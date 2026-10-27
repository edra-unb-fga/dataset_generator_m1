"""Host-only, registered artwork maps for qualitative planar plastic wear.

Maps express one deterministic surface state in artwork UV coordinates. Height is
only a bump signal: it neither deforms panel geometry nor changes its silhouette.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from .models import SurfaceWearConfig
from .surface_effects import apply_wear_fields, generate_wear_fields


MODEL = 'planar-wear-materials-v1'


def prepare_wear_maps(artwork: str | Path | np.ndarray, params: dict, seed: int,
                      output_dir: str | Path, *, roughness: float = .5) -> dict:
    """Write source-sized albedo, roughness and height PNGs and return their hashes.

    The albedo RGB follows ``SurfaceWear`` exactly, including its historical
    encoded-RGB mixing. RGBA input retains every original alpha byte. Grayscale
    roughness/height are linear data, not color textures. Strengths are qualitative
    and bounded by the validated wear configuration; no calibrated material claim
    is made. Renderer-side bump amplitude is recorded separately by the caller.
    """
    config = SurfaceWearConfig.model_validate(params)
    if not np.isfinite(roughness) or not 0 <= roughness <= 1:
        raise ValueError('roughness must be finite and between 0 and 1')
    if isinstance(artwork, (str, Path)):
        with Image.open(artwork) as image:
            source = np.asarray(image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')).copy()
    else:
        source = np.asarray(artwork)
    if source.dtype != np.uint8 or source.ndim != 3 or source.shape[2] not in (3, 4) or min(source.shape[:2]) < 1:
        raise ValueError('artwork must be a nonempty uint8 RGB or RGBA image')
    fields = generate_wear_fields(source.shape[:2], config, np.random.default_rng(seed))
    albedo = apply_wear_fields(source[:, :, :3], config, fields)
    if source.shape[2] == 4:
        albedo = np.dstack((albedo, source[:, :, 3]))
    # Dirt raises roughness and deposited height. Scratches lower both. A neutral
    # height of 128 supports conventional midlevel=.5 bump interpretation.
    rough = np.rint(np.clip(roughness+.35*fields.dirt[:, :, 0]-.10*fields.scratches[:, :, 0], 0, 1)*255).astype(np.uint8)
    height = np.rint(np.clip(.5+.08*fields.dirt[:, :, 0]-.12*fields.scratches[:, :, 0], 0, 1)*255).astype(np.uint8)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    maps = {}
    for name, array, encoding in (('albedo', albedo, 'srgb'), ('roughness', rough, 'linear'), ('height', height, 'linear')):
        path = destination/f'{name}.png'
        Image.fromarray(array).save(path)
        maps[name] = {'path': path.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'channels': ('RGBA' if array.shape[2] == 4 else 'RGB') if array.ndim == 3 else 'L',
                      'encoding': encoding, 'width': source.shape[1], 'height': source.shape[0], 'bit_depth': 8}
    return {'model': MODEL, 'seed': int(seed), 'config': config.model_dump(mode='json'),
            'shape': list(source.shape[:2]), 'maps': maps, 'local_marks': fields.evidence['local_marks'],
            'mapping': {'coordinates': 'artwork-uv', 'origin': 'top-left', 'height_role': 'bump-only'},
            'strength_bounds': {'base_roughness': roughness, 'roughness_dirt_gain': .35,
                                'roughness_scratch_gain': -.10, 'height_midlevel': .5,
                                'height_dirt_gain': .08, 'height_scratch_gain': -.12,
                                'height_render_scale': 'caller-recorded'},
            'source_sha256': hashlib.sha256(source.tobytes()).hexdigest()}
