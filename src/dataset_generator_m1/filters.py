from __future__ import annotations

import inspect
import os
from typing import Iterable

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("ALBUMENTATIONS_NO_TELEMETRY", "1")

import albumentations as A
import numpy as np

from .models import TransformSpec


SUPPORTED_TRANSFORMS = {
    "HueSaturationValue",
    "RandomBrightnessContrast",
    "GaussianBlur",
    "GaussNoise",
    "AdditiveNoise",
    "RandomGamma",
    "PlanckianJitter",
    "SaltAndPepper",
    "MotionBlur",
    "PlasmaShadow",
    "PlasmaBrightnessContrast",
    "RandomSunFlare",
    "Illumination",
}


def backend_version() -> str:
    return str(getattr(A, "__version__", "unknown"))


def validate_transform_specs(specs: Iterable[TransformSpec], stage: str) -> None:
    for spec in specs:
        if spec.type not in SUPPORTED_TRANSFORMS:
            raise ValueError(f"Unsupported Albumentations transform in {stage}: {spec.type}")
        transform_type = getattr(A, spec.type, None)
        if transform_type is None:
            raise ValueError(f"Installed Albumentations {backend_version()} lacks {spec.type} required by {stage}")
        signature = inspect.signature(transform_type)
        allowed = set(signature.parameters) - {"self", "p"}
        unknown = set(spec.params) - allowed
        if unknown:
            raise ValueError(
                f"Albumentations {backend_version()} does not accept {sorted(unknown)} for {stage}.{spec.type}; "
                f"allowed parameters: {sorted(allowed)}"
            )
        try:
            transform_type(**spec.params, p=1.0)
        except Exception as exc:
            raise ValueError(f"Invalid parameters for {stage}.{spec.type}: {exc}") from exc


def validate_appearance(background: Iterable[TransformSpec], foreground: Iterable[TransformSpec], final: Iterable[TransformSpec]) -> None:
    validate_transform_specs(background, "appearance.background")
    validate_transform_specs(foreground, "appearance.foreground")
    validate_transform_specs(final, "appearance.final")


def apply_pipeline(
    image: np.ndarray,
    specs: Iterable[TransformSpec],
    rng: np.random.Generator,
    *,
    preserve_alpha: bool = False,
) -> np.ndarray:
    specs = tuple(specs)
    if not specs:
        return image
    alpha: np.ndarray | None = None
    rgb = image
    if preserve_alpha:
        if image.ndim != 3 or image.shape[2] != 4:
            raise ValueError("preserve_alpha requires an RGBA image")
        rgb = image[:, :, :3].copy()
        alpha = image[:, :, 3].copy()
    for spec in specs:
        if rng.random() > spec.probability:
            continue
        transform_type = getattr(A, spec.type)
        transform = transform_type(**spec.params, p=1.0)
        rgb = transform(image=rgb)["image"]
    rgb = np.asarray(rgb, dtype=np.uint8)
    if alpha is None:
        return rgb
    result = np.dstack([rgb, alpha])
    result[alpha == 0, :3] = 0
    return result
