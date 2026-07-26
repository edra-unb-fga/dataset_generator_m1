from __future__ import annotations

from typing import Any

import numpy as np


ATMOSPHERIC_FOG_DEFAULTS: dict[str, Any] = {
    "density_range": (1.0, 3.0),
    "fog_color": (128, 128, 128),
    "depth_mode": "linear",
}
ATMOSPHERIC_FOG_PARAMETERS = frozenset(ATMOSPHERIC_FOG_DEFAULTS)
ATMOSPHERIC_FOG_DEPTH_MODES = frozenset({"linear", "diagonal", "radial"})


def validate_atmospheric_fog_params(params: dict[str, Any], stage: str) -> None:
    unknown = set(params) - ATMOSPHERIC_FOG_PARAMETERS
    if unknown:
        raise ValueError(
            f"Native AtmosphericFog does not accept {sorted(unknown)} for {stage}; "
            f"allowed parameters: {sorted(ATMOSPHERIC_FOG_PARAMETERS)}"
        )
    density_range = params.get("density_range", ATMOSPHERIC_FOG_DEFAULTS["density_range"])
    if not isinstance(density_range, (list, tuple)) or len(density_range) != 2:
        raise ValueError(f"{stage}.AtmosphericFog density_range must contain two numbers")
    low, high = density_range
    if not all(isinstance(value, (int, float)) for value in (low, high)) or low < 0 or high < low:
        raise ValueError(f"{stage}.AtmosphericFog density_range must be ordered and non-negative")
    fog_color = params.get("fog_color", ATMOSPHERIC_FOG_DEFAULTS["fog_color"])
    if (
        not isinstance(fog_color, (list, tuple))
        or len(fog_color) != 3
        or not all(isinstance(value, (int, float)) and 0 <= value <= 255 for value in fog_color)
    ):
        raise ValueError(f"{stage}.AtmosphericFog fog_color must be three values in [0, 255]")
    depth_mode = params.get("depth_mode", ATMOSPHERIC_FOG_DEFAULTS["depth_mode"])
    if depth_mode not in ATMOSPHERIC_FOG_DEPTH_MODES:
        raise ValueError(
            f"{stage}.AtmosphericFog depth_mode must be one of {sorted(ATMOSPHERIC_FOG_DEPTH_MODES)}"
        )


def _depth_map(height: int, width: int, mode: str) -> np.ndarray:
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    if mode == "linear":
        # The top of an outdoor image is treated as farther away than the bottom.
        return np.broadcast_to(1.0 - y, (height, width))
    if mode == "diagonal":
        # Top-left is farthest; bottom-right is nearest.
        return ((1.0 - y) + (1.0 - x)) * 0.5
    if mode == "radial":
        # The optical centre is near and the perimeter is progressively farther.
        dy = (y - 0.5) * 2.0
        dx = (x - 0.5) * 2.0
        return np.clip(np.sqrt(dx * dx + dy * dy) / np.sqrt(2.0), 0.0, 1.0)
    raise ValueError(f"Unknown AtmosphericFog depth mode: {mode}")


def apply_atmospheric_fog(
    image: np.ndarray,
    params: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply deterministic depth-dependent atmospheric scattering.

    This follows the public AtmosphericFog model:
    ``output = image * exp(-density * depth) + fog_color * (1 - transmission)``.
    """
    validate_atmospheric_fog_params(params, "appearance")
    density_range = params.get("density_range", ATMOSPHERIC_FOG_DEFAULTS["density_range"])
    fog_color = params.get("fog_color", ATMOSPHERIC_FOG_DEFAULTS["fog_color"])
    depth_mode = params.get("depth_mode", ATMOSPHERIC_FOG_DEFAULTS["depth_mode"])
    density = float(rng.uniform(float(density_range[0]), float(density_range[1])))
    depth = _depth_map(image.shape[0], image.shape[1], str(depth_mode))
    transmission = np.exp(-density * depth, dtype=np.float32)[..., None]
    source = np.asarray(image, dtype=np.float32)
    fog = np.asarray(fog_color, dtype=np.float32).reshape(1, 1, 3)
    rendered = source * transmission + fog * (1.0 - transmission)
    return np.clip(np.rint(rendered), 0, 255).astype(np.uint8), {
        "effect": "dataset_generator_m1.AtmosphericFog",
        "density": density,
        "depth_mode": str(depth_mode),
        "fog_color": [int(value) for value in fog_color],
    }
