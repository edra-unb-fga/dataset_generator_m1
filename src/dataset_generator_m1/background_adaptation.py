"""Broad scene-local colour adaptation for projected foregrounds."""

import math

import cv2
import numpy as np


def _sample(image: np.ndarray) -> np.ndarray:
    """Use a deterministic, bounded grid without allocating a full-size copy."""
    height, width = image.shape[:2]
    step = max(1, math.ceil(max(height, width) / 128))
    return image[::step, ::step]


def adapt_foreground_to_background(
    rgba: np.ndarray, background: np.ndarray, *,
    strength: float, radius_fraction: float, max_brightness_shift: float, max_color_shift: float,
) -> tuple[np.ndarray, dict]:
    """Adjust projected RGB using nearby background, leaving alpha untouched.

    Inputs are output-sized uint8 sRGB and alpha. The background must be the
    immutable projected background before any foreground compositing. Statistics
    use at most 128² grid samples. A spatially uniform channel shift avoids
    inventing a shadow; strength controls how broadly colours may change.
    """
    if (rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4 or not rgba.size
            or background.dtype != np.uint8 or background.shape != (*rgba.shape[:2], 3)):
        raise ValueError('expected matching nonempty uint8 RGB, alpha and background arrays')
    if not 0 <= strength <= 2 or not 0 <= radius_fraction <= .5 or not 0 <= max_brightness_shift <= 1 or not 0 <= max_color_shift <= 1:
        raise ValueError('strength and radius_fraction must be between 0 and 1')
    evidence = {'strength': float(strength), 'radius_fraction': float(radius_fraction),
                'foreground_samples': 0, 'background_samples': 0,
                'background_fallback': None, 'rgb_shift': [0., 0., 0.]}
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    result = rgba.copy()
    x, y, w, h = cv2.boundingRect(alpha)
    if not w or not h:
        evidence['background_fallback'] = 'empty_foreground'
        return result, evidence
    # Sample within support bounds so even tiny instances receive attention.
    foreground = _sample(rgb[y:y+h, x:x+w])
    weights = _sample(alpha[y:y+h, x:x+w]).astype(np.float32) / 255
    if not np.any(weights):
        # Sparse geometry can fall between grid points: use its strongest pixel.
        _, _, _, (px, py) = cv2.minMaxLoc(alpha[y:y+h, x:x+w])
        foreground = rgb[y+py:y+py+1, x+px:x+px+1]
        weights = alpha[y+py:y+py+1, x+px:x+px+1].astype(np.float32) / 255
    evidence['foreground_samples'] = int(np.count_nonzero(weights))
    fg_mean = (foreground.astype(np.float32) * weights[..., None]).sum(axis=(0, 1)) / weights.sum()
    radius = math.ceil(radius_fraction * max(alpha.shape))
    x0, y0 = max(0, x-radius), max(0, y-radius)
    x1, y1 = min(alpha.shape[1], x+w+radius), min(alpha.shape[0], y+h+radius)
    local_bg = _sample(background[y0:y1, x0:x1])
    outside = _sample(alpha[y0:y1, x0:x1]) == 0
    if not np.any(outside):
        evidence['background_fallback'] = 'no_local_background'
        return result, evidence
    evidence['background_samples'] = int(np.count_nonzero(outside))
    bg_mean = local_bg[outside].astype(np.float32).mean(axis=0)
    difference = (bg_mean - fg_mean) / 255
    luminance = float(difference @ np.array([.2126, .7152, .0722], dtype=np.float32))
    brightness = np.clip(strength * luminance, -max_brightness_shift, max_brightness_shift)
    chroma = np.clip(strength * (difference - luminance), -max_color_shift, max_color_shift)
    shift = 255 * (brightness + chroma)
    evidence['rgb_shift'] = [float(v) for v in shift]
    for top in range(y, y+h, 128):
        bottom = min(y+h, top+128)
        src = rgb[top:bottom, x:x+w]
        visible = alpha[top:bottom, x:x+w] != 0
        adjusted = np.clip(np.rint(src.astype(np.float32) + shift), 0, 255).astype(np.uint8)
        result[top:bottom, x:x+w, :3][visible] = adjusted[visible]
    return result, evidence
