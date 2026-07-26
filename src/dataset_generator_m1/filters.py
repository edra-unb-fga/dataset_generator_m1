from __future__ import annotations

import inspect
import hashlib
import json
import os
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any, Callable, Iterable

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("ALBUMENTATIONS_NO_TELEMETRY", "1")

import albumentations as A
import numpy as np

from .models import TransformSpec
from .native_effects import apply_atmospheric_fog, validate_atmospheric_fog_params


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
    "RandomFog",
    "RandomRain",
    "AtmosphericFog",
}

NATIVE_TRANSFORMS = {"AtmosphericFog"}


@dataclass(frozen=True)
class TransformTrace:
    id: str
    type: str
    stage: str
    applied: bool
    seed: int
    duration_ns: int
    input_pixels: int
    applied_params: tuple[dict[str, Any], ...]


def _effect_id(spec: TransformSpec, index: int) -> str:
    return spec.id or f"{index:02d}-{spec.type}"


def _effect_seed(base_seed: int, stage: str, effect_id: str) -> int:
    payload = f"{base_seed}:{stage}:{effect_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big", signed=False)


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        if value.size <= 32:
            return value.tolist()
        contiguous = np.ascontiguousarray(value)
        return {
            "kind": "ndarray-fingerprint",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "min": float(np.min(value)),
            "max": float(np.max(value)),
            "mean": float(np.mean(value)),
            "sha256": hashlib.sha256(contiguous.tobytes()).hexdigest(),
        }
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            candidate = np.asarray(value)
            if candidate.dtype != object and np.issubdtype(candidate.dtype, np.number):
                contiguous = np.ascontiguousarray(candidate)
                return {
                    "kind": "numeric-sequence-fingerprint",
                    "shape": list(candidate.shape),
                    "dtype": str(candidate.dtype),
                    "min": float(np.min(candidate)),
                    "max": float(np.max(candidate)),
                    "mean": float(np.mean(candidate)),
                    "sha256": hashlib.sha256(contiguous.tobytes()).hexdigest(),
                }
            return {
                "kind": "sequence-fingerprint",
                "length": len(value),
                "sha256": hashlib.sha256(repr(value).encode("utf-8")).hexdigest(),
            }
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def backend_version() -> str:
    return str(getattr(A, "__version__", "unknown"))


def validate_transform_specs(specs: Iterable[TransformSpec], stage: str) -> None:
    seen_ids: set[str] = set()
    for index, spec in enumerate(specs):
        effect_id = _effect_id(spec, index)
        if effect_id in seen_ids:
            raise ValueError(f"Duplicate transform id in {stage}: {effect_id}")
        seen_ids.add(effect_id)
        if spec.type not in SUPPORTED_TRANSFORMS:
            raise ValueError(f"Unsupported Albumentations transform in {stage}: {spec.type}")
        if spec.type == "AtmosphericFog":
            validate_atmospheric_fog_params(spec.params, stage)
            continue
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
        if spec.type == "AtmosphericFog":
            rgb, _ = apply_atmospheric_fog(rgb, spec.params, rng)
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


def apply_pipeline_traced(
    image: np.ndarray,
    specs: Iterable[TransformSpec],
    base_seed: int,
    stage: str,
    *,
    preserve_alpha: bool = False,
    clock: Callable[[], int] = perf_counter_ns,
) -> tuple[np.ndarray, tuple[TransformTrace, ...]]:
    """Apply appearance effects with order-independent random streams and traces.

    Each effect owns a deterministic stream derived from its stable ID. Inserting or
    removing another effect therefore cannot perturb activation or sampled parameters.
    """
    specs = tuple(specs)
    alpha: np.ndarray | None = None
    rgb = image
    if preserve_alpha:
        if image.ndim != 3 or image.shape[2] != 4:
            raise ValueError("preserve_alpha requires an RGBA image")
        rgb = image[:, :, :3].copy()
        alpha = image[:, :, 3].copy()
    traces: list[TransformTrace] = []
    pixels = int(image.shape[0] * image.shape[1])
    for index, spec in enumerate(specs):
        effect_id = _effect_id(spec, index)
        seed = _effect_seed(base_seed, stage, effect_id)
        activation_rng = np.random.default_rng(seed)
        applied = bool(activation_rng.random() <= spec.probability)
        started = clock()
        applied_params: tuple[dict[str, Any], ...] = ()
        if applied:
            if spec.type == "AtmosphericFog":
                rgb, sampled = apply_atmospheric_fog(rgb, spec.params, activation_rng)
                applied_params = (_json_safe(sampled),)
            else:
                transform_type = getattr(A, spec.type)
                transform = transform_type(**spec.params, p=1.0)
                composed = A.Compose([transform], seed=seed, save_applied_params=True)
                payload = composed(image=rgb)
                rgb = payload["image"]
                applied_params = tuple(_json_safe(item) for item in payload.get("applied_transforms", ()))
        duration = max(0, clock() - started)
        traces.append(
            TransformTrace(
                id=effect_id,
                type=spec.type,
                stage=stage,
                applied=applied,
                seed=seed,
                duration_ns=duration,
                input_pixels=pixels,
                applied_params=applied_params,
            )
        )
    rgb = np.asarray(rgb, dtype=np.uint8)
    if alpha is None:
        return rgb, tuple(traces)
    result = np.dstack([rgb, alpha])
    result[alpha == 0, :3] = 0
    return result, tuple(traces)
