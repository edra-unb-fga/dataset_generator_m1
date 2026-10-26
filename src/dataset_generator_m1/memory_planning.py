"""Phase/lifetime RAM accounting, independent of one host's throughput measurements."""
from functools import lru_cache
import math

from PIL import Image

from .assets import discover_images
from .backgrounds import _release_schedule

MIB = 1024**2
MODEL_VERSION = "phase-lifetimes-v3"
HEADROOM_PERCENT = 20


@lru_cache(maxsize=4096)
def _dimensions(path, size, mtime_ns):
    # Cache metadata, never decoded pixels. File changes invalidate this key.
    with Image.open(path) as image:
        return image.size


def source_shapes(resolved):
    width, height = resolved.profile.output.image_size
    scale = resolved.profile.scene.canvas_scale
    cw, ch = round(width * scale), round(height * scale)
    canvas = cw * ch
    pixels = {"backgrounds": 0, "foregrounds": 0}
    cover = canvas
    resize_peak = 0
    rotated = 0
    aspect = 1.
    unknown = False
    for role in pixels:
        source = getattr(resolved.profile.assets, role)
        paths = discover_images(list(source.paths), source.recursive)
        if not paths:
            unknown = True
        for path in paths:
            try:
                stat = path.stat()
                w, h = _dimensions(str(path), stat.st_size, stat.st_mtime_ns)
                pixels[role] = max(pixels[role], w * h)
                if role == "backgrounds":
                    factor = max(cw / w, ch / h)
                    expanded = math.ceil(w * factor) * math.ceil(h * factor)
                    cover = max(cover, expanded)
                    # Loading has two float32 RGB copies; resize holds source,
                    # expanded raster and crop together. Keep each asset's
                    # dimensions correlated instead of combining unrelated maxima.
                    resize_peak = max(resize_peak, 24*w*h, 12*(w*h + expanded + canvas))
                else:
                    rotated = max(rotated, math.ceil((w+h)**2 / 2))
                    aspect = max(aspect, w/h, h/w)
            except (OSError, ValueError, Image.DecompressionBombError):
                unknown = True
    bg = pixels["backgrounds"] or 2*width*height
    fg = pixels["foregrounds"] or 2*width*height
    return {
        "background_pixels": bg, "foreground_pixels": fg,
        "cover_pixels": cover, "background_resize_peak_bytes": resize_peak or max(24*bg,12*(bg+cover+canvas)),
        "foreground_rotated_pixels": rotated or 2*fg, "foreground_max_aspect": aspect,
        "unknown_sources": unknown,
    }


def recipe_peak_bytes(recipe, canvas, shapes):
    """Use the renderer's last-use schedule and count live arrays + operation scratch.

    Stored values are bytes per canvas pixel. Asset handles own no raster. RGB is
    float32 except linear blending/propagation of a float64 scalar mask. Operator
    allowances include their result; they are not added again as output storage.
    """
    releases = _release_schedule(recipe)
    live = {}
    peak = 0
    for index, node in enumerate(recipe.nodes):
        inputs = {name: live[reference] for name, reference in node.inputs.items()}
        op = node.op
        result = 12
        extra = 0
        if op == "sample_asset":
            result = 0
        elif op == "resize_crop":
            result = inputs["image"] or 12
            extra = shapes["background_resize_peak_bytes"] if not inputs["image"] else 2*result*canvas
        elif op == "texture_map":
            result = inputs["image"] or 12
            extra = max(24*shapes['background_pixels'],12*shapes['background_pixels']+48*canvas) if not inputs['image'] else (36+result)*canvas
        elif op == "channel_extract":
            result = 4
            extra = (32 + (12 if inputs['image']>12 else 0))*canvas
        elif op == "mask_normalize":
            result = 8
            extra = 32*canvas
        elif op == "palette_transfer":
            extra = (72 + 12*sum(v>12 for v in inputs.values()))*canvas
        elif op == "multiband_blend":
            # Streamed pyramids/reconstruction: allow72 B/px for live pyramid
            # levels, Laplacians, prior result and simultaneous blend-expression
            # temporaries (including Python3.14's longer temporary lifetimes);
            # float64 inputs retain their originals while level-zero float32
            # conversions add4 B/px for the mask and12 B/px for each RGB input.
            extra = (72 + (4 if inputs['mask']>4 else 0)
                     + 12*sum(inputs[name]>12 for name in ('first','second')))*canvas
        elif op == "displace":
            result = inputs['image']
            extra = (64 + max(0,result-12))*canvas
        elif op == "linear_blend":
            result = max(inputs['first'],inputs['second'],3*inputs['mask'])
            extra = (3*result+inputs['mask'])*canvas
        elif op == "channel_compose":
            extra = 36*canvas
        elif op == "colorspace_convert":
            passthrough = str(node.params.get('from','RGB')).lower()=='rgb' and str(node.params.get('to','RGB')).lower()=='rgb'
            result = inputs['image'] if passthrough else 12
            extra = 0 if passthrough else (36 + (12 if inputs['image']>12 else 0))*canvas
        else:
            raise ValueError(f'No memory accounting for recipe operation {op}')
        peak = max(peak, sum(live.values())*canvas + extra)
        live[node.id] = result
        for name in releases[index]:
            del live[name]
    output = live[recipe.output] or 12
    if not live[recipe.output]:
        peak = max(peak, shapes['background_resize_peak_bytes'])
    # Original graph output, clipped float32 output, QA colour/luminance/statistic
    # arrays. QA is a later phase; synthesis scratch is already released.
    return max(peak, (output+12+48)*canvas)


def memory_components(resolved, workers, window, native_threads, shapes):
    width, height = resolved.profile.output.image_size
    output = width * height
    scale = resolved.profile.scene.canvas_scale
    cw, ch = round(width*scale), round(height*scale)
    canvas = cw*ch
    instances = resolved.profile.sampling.instances_per_image[1]
    weights = resolved.profile.background_synthesis.recipe_weights
    selected = {name:recipe for name,recipe in resolved.recipes.recipes.items() if weights.get(name,0)>0}
    selected = selected or resolved.recipes.recipes
    recipes = {name:recipe_peak_bytes(recipe,canvas,shapes) for name,recipe in selected.items()}
    background = max(recipes.values(), default=72*canvas)
    # Foreground effects, rotation and resize run sequentially, after synthesis.
    target_width = max(1,math.ceil(cw*resolved.profile.scene.camera.crop_scale[1]*resolved.profile.sampling.foreground_size[1]))
    resized = math.ceil(target_width**2*shapes['foreground_max_aspect'])
    foreground = max(64*shapes['foreground_pixels'],
        4*(shapes['foreground_pixels']+shapes['foreground_rotated_pixels']),
        4*(shapes['foreground_rotated_pixels']+resized))
    retained_render = 7*canvas + (3+2*instances)*output
    render = max(41*canvas+3*output, retained_render+foreground+52*output)
    if resolved.profile.scene.foreground_resampling == "premultiplied":
        # Float packed premultiplication/filter/unpremultiplication plus integer alpha.
        foreground = max(foreground, 40*(shapes['foreground_pixels']+shapes['foreground_rotated_pixels']),
                         40*(shapes['foreground_rotated_pixels']+resized))
        render = max(render, retained_render+foreground+80*output)
    if resolved.profile.scene.lighting is not None:
        render = max(render,retained_render+width*min(height,128)*40+output*3)
    if resolved.profile.scene.occlusion is not None:
        render = max(render,retained_render+output*52)
    evidence = 3*canvas+(32+6*instances)*output
    phases = {'background':background,'scene_render':render,'mask_evidence':evidence}
    worker_peak = max(phases.values())
    # Runtime reserves remain256 MiB per process; the revision removes dead
    # buffers and mutually exclusive phases rather than fitting a smaller baseline.
    runtime = (1 if workers==1 else workers+1)*256*MIB
    native = workers*max(0,native_threads-1)*2*MIB
    coordinator = output*40
    queued = 2*(1 if workers==1 else window)*output*(3+2*instances)
    subtotal = runtime+native+coordinator+workers*worker_peak+queued
    headroom = (subtotal*HEADROOM_PERCENT+99)//100
    return {
        'model_version':MODEL_VERSION,'estimate_metric':'process-tree RSS planning upper estimate',
        'runtime_reserve_bytes':runtime,'native_reserve_bytes':native,
        'coordinator_reserve_bytes':coordinator,'worker_peak_bytes':worker_peak,
        'phase_peaks_bytes_per_worker':phases,'recipe_peaks_bytes':recipes,
        'queued_result_bytes':queued,'headroom_percent':HEADROOM_PERCENT,'headroom_bytes':headroom,
        'estimated_peak_bytes':subtotal+headroom,'source_dimensions_complete':not shapes['unknown_sources'],
    }
