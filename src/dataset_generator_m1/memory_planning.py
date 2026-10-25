"""Conservative shape accounting, not a fitted RSS prediction or an OS memory limit."""
from functools import lru_cache
import math

from PIL import Image

from .assets import discover_images

MIB = 1024**2
MODEL_VERSION = "shape-reserves-v2"


@lru_cache(maxsize=4096)
def _dimensions(path, size, mtime_ns):
    # File metadata participates in the cache key; never retain decoded pixels.
    with Image.open(path) as image:
        return image.size


def source_shapes(resolved):
    width, height = resolved.profile.output.image_size
    scale = resolved.profile.scene.canvas_scale
    canvas_width, canvas_height = round(width * scale), round(height * scale)
    pixels = {"backgrounds": 0, "foregrounds": 0}
    cover = canvas_width * canvas_height
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
                    factor = max(canvas_width / w, canvas_height / h)
                    cover = max(cover, math.ceil(w * factor) * math.ceil(h * factor))
            except (OSError, ValueError, Image.DecompressionBombError):
                unknown = True
    # Missing/unreadable sources are diagnosed by catalog validation. Keep the
    # advisory planner usable, and explicitly report uncertainty in this fallback.
    return {
        "background_pixels": pixels["backgrounds"] or 2 * width * height,
        "foreground_pixels": pixels["foregrounds"] or 2 * width * height,
        "cover_pixels": cover,
        "unknown_sources": unknown,
    }


def _graph_storage(recipe):
    total = 0
    for node in recipe.nodes:
        if node.op == "sample_asset":
            continue
        if node.op in {"channel_extract", "mask_normalize"}:
            total += 8
        elif node.op == "linear_blend":
            total += 24
        else:
            total += 12
    return total


def memory_components(resolved, workers, window, native_threads, shapes):
    width, height = resolved.profile.output.image_size
    output = width * height
    scale = resolved.profile.scene.canvas_scale
    canvas = round(width * scale) * round(height * scale)
    instances = resolved.profile.sampling.instances_per_image[1]
    # Reserve all declared graph outputs, even though production releases dead
    # nodes, plus operator scratch. Scalar normalization can promote to float64;
    # linear blending can consequently produce float64 RGB.
    graph_bytes_per_pixel = max((_graph_storage(recipe) for recipe in resolved.recipes.recipes.values()), default=0)
    workspace = canvas * max(96, graph_bytes_per_pixel + 64)
    source = shapes["background_pixels"] * 24 + shapes["foreground_pixels"] * 64
    cover_extra = max(0, shapes["cover_pixels"] - canvas) * 24
    masks = output * instances * 8
    effects = 0
    if resolved.profile.scene.lighting is not None:
        effects += width * min(height, 128) * 40 + output * 3
    if resolved.profile.scene.occlusion is not None:
        effects += output * 52
    # Process reserves cover interpreter/native runtime and retained allocations.
    # Native reserve is committed-memory headroom, not a prediction of stack RSS.
    process_count = 1 if workers == 1 else workers + 1
    runtime = process_count * 256 * MIB
    native = workers * max(0, native_threads - 1) * 2 * MIB
    coordinator = output * 40
    # Returned RGB + worst-case raw full/visible coverage, with a second copy for
    # serialization/receipt. Actual mask archives are usually much smaller.
    queued = 2 * window * output * (3 + 2 * instances)
    per_worker = workspace + source + cover_extra + masks + effects
    subtotal = runtime + native + coordinator + workers * per_worker + queued
    headroom = (subtotal + 3) // 4
    return {
        "model_version": MODEL_VERSION,
        "runtime_reserve_bytes": runtime,
        "native_reserve_bytes": native,
        "coordinator_reserve_bytes": coordinator,
        "workspace_bytes_per_worker": workspace,
        "source_bytes_per_worker": source,
        "cover_extra_bytes_per_worker": cover_extra,
        "mask_bytes_per_worker": masks,
        "scene_effect_bytes_per_worker": effects,
        "queued_result_bytes": queued,
        "headroom_bytes": headroom,
        "estimated_peak_bytes": subtotal + headroom,
        "source_dimensions_complete": not shapes["unknown_sources"],
    }
