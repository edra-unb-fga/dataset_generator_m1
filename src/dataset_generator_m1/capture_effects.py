"""Reproducible whole-image capture effects shared by image workflows."""
from __future__ import annotations

import math

import albumentations as A
import numpy as np


def validate_weighted_motion(params, stage):
    if stage not in ('final', 'appearance.final'):
        raise ValueError('WeightedMotionBlur is a final-image capture effect')
    if not {'kernels', 'weights'} <= set(params) or set(params) - {'kernels', 'weights', 'reference_size'}:
        raise ValueError('WeightedMotionBlur requires kernels and weights, and optionally reference_size')
    if 'reference_size' in params:
        reference = params['reference_size']
        if isinstance(reference, bool) or not isinstance(reference, int) or reference < 1:
            raise ValueError('reference_size must be a positive integer')
    kernels, weights = params['kernels'], params['weights']
    if not isinstance(kernels, (list, tuple)) or not isinstance(weights, (list, tuple)) or not kernels or len(kernels) != len(weights):
        raise ValueError('kernels and weights must be nonempty lists of equal length')
    if any(isinstance(k, bool) or not isinstance(k, int) or k < 3 or k > 255 or k % 2 == 0 for k in kernels):
        raise ValueError('motion kernels must be odd integers between 3 and 255')
    if len(set(kernels)) != len(kernels):
        raise ValueError('motion kernels must be unique')
    if any(isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError('motion weights must be finite, nonnegative and not all zero')


def apply_weighted_motion(rgb, params, rng):
    validate_weighted_motion(params, 'final')
    weights = np.asarray(params['weights'], dtype=np.float64)
    # Preserve ordinary distributions exactly, while avoiding overflow for
    # individually finite but extremely large weights.
    with np.errstate(over='ignore'):
        total = weights.sum()
    if not np.isfinite(total):
        weights = weights / weights.max()
        total = weights.sum()
    index = int(rng.choice(len(weights), p=weights / total))
    kernel = params['kernels'][index]
    seed = int(rng.integers(0, 2**32, dtype=np.uint32))
    if 'reference_size' in params:
        reference = params['reference_size']
        height, width = rgb.shape[:2]
        shortest = min(height, width)
        # Nearest positive odd integer; an even value is a tie resolved upward.
        rounded = 2 * (kernel * shortest // (2 * reference)) + 1
        limit = max(1, min(255, shortest if shortest % 2 else shortest - 1))
        effective = min(rounded, limit)
        trace = {'configured_kernel': kernel, 'effective_kernel': effective,
                 'kernel': effective, 'reference_size': reference,
                 'output_dimensions': [width, height], 'scale': shortest / reference,
                 'clamp_reason': 'supported-or-image-bound' if effective != rounded else None,
                 'noop_reason': 'effective-kernel-one' if effective == 1 else None,
                 'transform_seed': seed}
        if effective == 1:
            return rgb, {**trace, 'applied_transforms': []}
        transform = A.Compose([A.MotionBlur(blur_limit=(effective, effective), allow_shifted=False, p=1)], seed=seed, save_applied_params=True)
        result = transform(image=rgb)
        return result['image'], {**trace, 'applied_transforms': result.get('applied_transforms', [])}
    transform = A.Compose([A.MotionBlur(blur_limit=(kernel, kernel), allow_shifted=False, p=1)], seed=seed, save_applied_params=True)
    result = transform(image=rgb)
    return result['image'], {'kernel': kernel, 'transform_seed': seed, 'applied_transforms': result.get('applied_transforms', [])}
