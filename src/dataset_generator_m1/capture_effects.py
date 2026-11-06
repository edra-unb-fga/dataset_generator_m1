"""Reproducible whole-image capture effects shared by image workflows."""
from __future__ import annotations

import math

import albumentations as A
import numpy as np


def validate_weighted_motion(params, stage):
    if stage not in ('final', 'appearance.final'):
        raise ValueError('WeightedMotionBlur is a final-image capture effect')
    if set(params) != {'kernels', 'weights'}:
        raise ValueError('WeightedMotionBlur requires kernels and weights')
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
    index = int(rng.choice(len(weights), p=weights / weights.sum()))
    kernel = params['kernels'][index]
    seed = int(rng.integers(0, 2**32, dtype=np.uint32))
    transform = A.Compose([A.MotionBlur(blur_limit=(kernel, kernel), allow_shifted=False, p=1)], seed=seed, save_applied_params=True)
    result = transform(image=rgb)
    return result['image'], {'kernel': kernel, 'transform_seed': seed, 'applied_transforms': result.get('applied_transforms', [])}
