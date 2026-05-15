from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULTS: dict[str, Any] = {
    "dataset_type": "manometro",
    "num_images": 10,
    "output_dir": "outputs/generated",
    "debug": 0,
    "debug_dir": "debug",
    "seed": 42,
    "paths": {
        "backgrounds_dir": "backgrounds",
        "foregrounds_dir": None,
        "recursive_backgrounds": True,
    },
    "output": {
        "image_size": [1280, 1280],
        "image_format": "jpg",
        "label_format": "yolo",
        "write_data_yaml": True,
        "write_manifest": True,
    },
    "sampling": {
        "foreground_instances_range": [1, 2],
        "foreground_scale_range": [0.20, 0.45],
        "min_instance_distance_px": 20,
        "max_placement_attempts": 50,
        "final_crop_size_range": [1280, 1280],
    },
    "perspective_transformations": {
        "probability": 0.25,
        "scale_range": [0.0, 0.02],
        "shear_range": [-0.015, 0.015],
    },
    "background_affine_transformations": {
        "rotation": {"angle_range": [-6, 6], "probability": 0.35},
        "scaling": {"scale_range": [0.96, 1.06], "probability": 0.35},
        "translation": {"translate_range": [-0.04, 0.04], "probability": 0.2},
    },
    "foreground_affine_transformations": {
        "rotation": {"mode": "square", "angle_range": [-35, 35], "probability": 0.8}
    },
    "background_filters": {},
    "foreground_filters": {},
    "final_filters": {},
}

DATASET_FOREGROUND_DEFAULTS = {
    "manometro": "foregrounds/manometro_foregrounds",
    "landing": "foregrounds/landing_foregrounds",
}

DATASET_ROTATION_DEFAULTS = {
    "manometro": {"mode": "square", "angle_range": [-35, 35], "probability": 0.8},
    "landing": {"mode": "circle", "angle_range": [-180, 180], "probability": 1.0},
}

ALLOWED_TOP_LEVEL = set(DEFAULTS)
ALLOWED_OVERRIDES = {
    "dataset_type",
    "num_images",
    "output_dir",
    "debug",
    "debug_dir",
    "backgrounds_dir",
}

ALLOWED_NESTED_KEYS = {
    "paths": {"backgrounds_dir", "foregrounds_dir", "recursive_backgrounds"},
    "output": {"image_size", "image_format", "label_format", "write_data_yaml", "write_manifest"},
    "sampling": {
        "foreground_instances_range",
        "foreground_scale_range",
        "min_instance_distance_px",
        "max_placement_attempts",
        "final_crop_size_range",
    },
    "perspective_transformations": {"probability", "scale_range", "shear_range"},
}

ALLOWED_GEOMETRY_KEYS = {
    "background_affine_transformations": {
        "rotation": {"angle_range", "probability"},
        "scaling": {"scale_range", "probability"},
        "translation": {"translate_range", "probability"},
    },
    "foreground_affine_transformations": {
        "rotation": {"mode", "angle_range", "probability"},
    },
}

ALLOWED_FILTER_PARAMS = {
    "HueSaturationValue": {"hue_shift_range", "sat_shift_range", "val_shift_range", "probability"},
    "RandomBrightnessContrast": {"brightness_range", "contrast_range", "brightness_by_max", "ensure_safe_output", "probability"},
    "GaussianBlur": {"blur_limit", "sigma_limit", "probability"},
    "GaussNoise": {"std_range", "mean_range", "per_channel", "probability"},
    "AdditiveNoise": {"noise_type", "spatial_mode", "noise_params", "std_range", "mean_range", "probability"},
    "RandomGamma": {"gamma_range", "probability"},
    "PlanckianJitter": {"mode", "temperature_range", "sampling_method", "probability"},
    "SaltAndPepper": {"amount_range", "salt_vs_pepper_range", "probability"},
    "MotionBlur": {"blur_range", "allow_shifted", "angle_range", "direction_range", "probability"},
    "PlasmaShadow": {"shadow_intensity_range", "plasma_size", "roughness", "probability"},
    "PlasmaBrightnessContrast": {"brightness_range", "contrast_range", "plasma_size", "roughness", "probability"},
    "RandomSunFlare": {"flare_roi", "src_radius", "src_color", "angle_range", "num_flare_circles_range", "method", "probability"},
    "Illumination": {"mode", "intensity_range", "effect_type", "angle_range", "center_range", "sigma_range", "probability"},
    "AtmosphericFog": {"density_range", "fog_color", "depth_mode", "probability"},
}


@dataclass(frozen=True)
class GeneratorConfig:
    data: dict[str, Any]
    config_path: Path | None = None

    @property
    def dataset_type(self) -> str:
        return self.data["dataset_type"]

    @property
    def num_images(self) -> int:
        return int(self.data["num_images"])

    @property
    def output_dir(self) -> Path:
        return Path(self.data["output_dir"])

    @property
    def debug_count(self) -> int:
        return int(self.data.get("debug") or 0)

    @property
    def image_size(self) -> tuple[int, int]:
        width, height = self.data["output"]["image_size"]
        return int(width), int(height)


def load_config(path: str | Path | None, overrides: dict[str, Any] | None = None) -> GeneratorConfig:
    config_path = Path(path) if path else None
    raw: dict[str, Any] = {}
    if config_path:
        with config_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Config must be a YAML mapping: {config_path}")
            raw = loaded

    unknown = set(raw) - ALLOWED_TOP_LEVEL
    if unknown:
        raise ValueError(f"Unknown top-level config keys: {sorted(unknown)}")

    merged = deepcopy(DEFAULTS)
    deep_merge(merged, raw)
    apply_overrides(merged, overrides or {})
    apply_dataset_defaults(merged)
    validate_config(merged)
    return GeneratorConfig(data=merged, config_path=config_path)


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def apply_overrides(config: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if value is None:
            continue
        if key not in ALLOWED_OVERRIDES:
            raise ValueError(f"Unsupported CLI override: {key}")
        if key == "backgrounds_dir":
            config["paths"]["backgrounds_dir"] = value
        else:
            config[key] = value


def apply_dataset_defaults(config: dict[str, Any]) -> None:
    dataset_type = config["dataset_type"]
    if dataset_type not in DATASET_FOREGROUND_DEFAULTS:
        raise ValueError("dataset_type must be 'manometro' or 'landing'")
    if not config["paths"].get("foregrounds_dir"):
        config["paths"]["foregrounds_dir"] = DATASET_FOREGROUND_DEFAULTS[dataset_type]

    user_rotation = config.get("foreground_affine_transformations", {}).get("rotation", {})
    default_rotation = deepcopy(DATASET_ROTATION_DEFAULTS[dataset_type])
    default_rotation.update(user_rotation)
    config["foreground_affine_transformations"]["rotation"] = default_rotation


def validate_config(config: dict[str, Any]) -> None:
    validate_known_keys(config)
    if int(config["num_images"]) < 1:
        raise ValueError("num_images must be >= 1")
    if config["output"]["label_format"] != "yolo":
        raise ValueError("Only output.label_format='yolo' is supported")
    if config["output"]["image_format"].lower() not in {"jpg", "jpeg", "png"}:
        raise ValueError("output.image_format must be jpg, jpeg, or png")
    validate_pair(config["output"]["image_size"], "output.image_size", minimum=1)
    validate_pair(config["sampling"]["foreground_instances_range"], "sampling.foreground_instances_range", minimum=0)
    validate_pair(config["sampling"]["foreground_scale_range"], "sampling.foreground_scale_range", minimum=0.001)
    validate_pair(config["sampling"]["final_crop_size_range"], "sampling.final_crop_size_range", minimum=1)
    if int(config["sampling"]["max_placement_attempts"]) < 1:
        raise ValueError("sampling.max_placement_attempts must be >= 1")
    if config["foreground_affine_transformations"]["rotation"]["mode"] not in {"square", "circle"}:
        raise ValueError("foreground_affine_transformations.rotation.mode must be square or circle")
    validate_filter_groups(config.get("background_filters", {}), "background_filters")
    validate_filter_groups(config.get("foreground_filters", {}), "foreground_filters")
    validate_filter_groups(config.get("final_filters", {}), "final_filters")


def validate_known_keys(config: dict[str, Any]) -> None:
    for section, allowed in ALLOWED_NESTED_KEYS.items():
        unknown = set(config.get(section, {})) - allowed
        if unknown:
            raise ValueError(f"Unknown keys in {section}: {sorted(unknown)}")
    for section, transforms in ALLOWED_GEOMETRY_KEYS.items():
        section_data = config.get(section, {})
        unknown_transforms = set(section_data) - set(transforms)
        if unknown_transforms:
            raise ValueError(f"Unknown transforms in {section}: {sorted(unknown_transforms)}")
        for transform, allowed_keys in transforms.items():
            unknown = set(section_data.get(transform, {})) - allowed_keys
            if unknown:
                raise ValueError(f"Unknown keys in {section}.{transform}: {sorted(unknown)}")


def validate_filter_groups(groups: dict[str, Any], section: str) -> None:
    if not isinstance(groups, dict):
        raise ValueError(f"{section} must be a mapping")
    for group_name, transforms in groups.items():
        if not isinstance(transforms, dict):
            raise ValueError(f"{section}.{group_name} must be a mapping")
        for transform_name, params in transforms.items():
            if transform_name not in ALLOWED_FILTER_PARAMS:
                raise ValueError(f"Unsupported filter in {section}: {transform_name}")
            if not isinstance(params, dict):
                raise ValueError(f"{section}.{group_name}.{transform_name} must be a mapping")
            unknown = set(params) - ALLOWED_FILTER_PARAMS[transform_name]
            if unknown:
                raise ValueError(f"Unknown keys in {section}.{group_name}.{transform_name}: {sorted(unknown)}")


def validate_pair(value: Any, name: str, minimum: float | int | None = None) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be a two-item list")
    if minimum is not None and (value[0] < minimum or value[1] < minimum):
        raise ValueError(f"{name} values must be >= {minimum}")
    if value[0] > value[1]:
        raise ValueError(f"{name} must be ordered [min, max]")
