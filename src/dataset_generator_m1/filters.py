from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")

import albumentations as A
import cv2
import numpy as np

SUPPORTED_FILTERS = {
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
    "AtmosphericFog",
}

ALBUMENTATIONS_FILTERS = {
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


def apply_filter_groups(image: np.ndarray, groups: dict[str, Any], rng: np.random.Generator, preserve_alpha: bool = False) -> np.ndarray:
    if not groups:
        return image

    alpha = None
    rgb = image
    if preserve_alpha and image.shape[2] == 4:
        rgb = image[:, :, :3].copy()
        alpha = image[:, :, 3].copy()

    for transforms in groups.values():
        if not isinstance(transforms, dict):
            raise ValueError("Filter groups must contain transform dictionaries")
        for name, params in transforms.items():
            if name not in SUPPORTED_FILTERS:
                raise ValueError(f"Unsupported filter: {name}")
            if not isinstance(params, dict):
                raise ValueError(f"Filter {name} must be a mapping")
            probability = float(params.get("probability", 0.0))
            if rng.random() <= probability:
                rgb = apply_named_filter(name, rgb, params, rng)

    if alpha is None:
        return rgb
    out = np.dstack([rgb, alpha])
    out[alpha == 0, :3] = 0
    return out


def apply_named_filter(name: str, image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    if name in ALBUMENTATIONS_FILTERS:
        return apply_albumentations_filter(name, image, params)
    if name == "HueSaturationValue":
        return hue_saturation_value(image, params, rng)
    if name == "RandomBrightnessContrast":
        return brightness_contrast(image, params, rng)
    if name == "GaussianBlur":
        return gaussian_blur(image, params, rng)
    if name in {"GaussNoise", "AdditiveNoise"}:
        return additive_noise(image, params, rng)
    if name == "RandomGamma":
        return random_gamma(image, params, rng)
    if name == "PlanckianJitter":
        return planckian_jitter(image, params, rng)
    if name == "SaltAndPepper":
        return salt_and_pepper(image, params, rng)
    if name == "MotionBlur":
        return motion_blur(image, params, rng)
    if name == "PlasmaShadow":
        return plasma_shadow(image, params, rng)
    if name == "PlasmaBrightnessContrast":
        return plasma_brightness_contrast(image, params, rng)
    if name == "RandomSunFlare":
        return random_sun_flare(image, params, rng)
    if name == "Illumination":
        return illumination(image, params, rng)
    if name == "AtmosphericFog":
        return atmospheric_fog(image, params, rng)
    return image


def apply_albumentations_filter(name: str, image: np.ndarray, params: dict[str, Any]) -> np.ndarray:
    transform = build_albumentations_transform(name, params)
    return transform(image=image)["image"]


def build_albumentations_transform(name: str, params: dict[str, Any]) -> A.ImageOnlyTransform:
    if name == "HueSaturationValue":
        return A.HueSaturationValue(
            hue_shift_limit=tuple(params.get("hue_shift_range", [-6, 6])),
            sat_shift_limit=tuple(params.get("sat_shift_range", [-18, 18])),
            val_shift_limit=tuple(params.get("val_shift_range", [-12, 12])),
            p=1.0,
        )
    if name == "RandomBrightnessContrast":
        return A.RandomBrightnessContrast(
            brightness_limit=tuple(params.get("brightness_range", [-0.12, 0.12])),
            contrast_limit=tuple(params.get("contrast_range", [-0.12, 0.12])),
            brightness_by_max=bool(params.get("brightness_by_max", True)),
            ensure_safe_range=bool(params.get("ensure_safe_output", True)),
            p=1.0,
        )
    if name == "GaussianBlur":
        return A.GaussianBlur(
            blur_limit=tuple(params.get("blur_limit", [3, 5])),
            sigma_limit=tuple(params.get("sigma_limit", [0.0, 0.6])),
            p=1.0,
        )
    if name == "GaussNoise":
        return A.GaussNoise(
            std_range=tuple(params.get("std_range", [0.0, 0.06])),
            mean_range=tuple(params.get("mean_range", [0.0, 0.0])),
            per_channel=bool(params.get("per_channel", False)),
            p=1.0,
        )
    if name == "AdditiveNoise":
        return A.AdditiveNoise(
            noise_type=params.get("noise_type", "gaussian"),
            spatial_mode=params.get("spatial_mode", "shared"),
            noise_params=params.get("noise_params"),
            p=1.0,
        )
    if name == "RandomGamma":
        return A.RandomGamma(gamma_limit=tuple(params.get("gamma_range", [90, 110])), p=1.0)
    if name == "PlanckianJitter":
        return A.PlanckianJitter(
            mode=params.get("mode", "blackbody"),
            temperature_limit=tuple(params.get("temperature_range", [5000, 8500])),
            sampling_method=params.get("sampling_method", "uniform"),
            p=1.0,
        )
    if name == "SaltAndPepper":
        return A.SaltAndPepper(
            amount=tuple(params.get("amount_range", [0.0, 0.01])),
            salt_vs_pepper=tuple(params.get("salt_vs_pepper_range", [0.45, 0.55])),
            p=1.0,
        )
    if name == "MotionBlur":
        return A.MotionBlur(
            blur_limit=tuple(params.get("blur_range", [3, 5])),
            allow_shifted=bool(params.get("allow_shifted", True)),
            angle_range=tuple(params.get("angle_range", [-12, 12])),
            direction_range=tuple(params.get("direction_range", [-0.2, 0.2])),
            p=1.0,
        )
    if name == "PlasmaShadow":
        return A.PlasmaShadow(
            shadow_intensity_range=tuple(params.get("shadow_intensity_range", [0.1, 0.35])),
            plasma_size=int(params.get("plasma_size", 256)),
            roughness=float(params.get("roughness", 3.0)),
            p=1.0,
        )
    if name == "PlasmaBrightnessContrast":
        return A.PlasmaBrightnessContrast(
            brightness_range=tuple(params.get("brightness_range", [-0.08, 0.08])),
            contrast_range=tuple(params.get("contrast_range", [-0.08, 0.08])),
            plasma_size=int(params.get("plasma_size", 256)),
            roughness=float(params.get("roughness", 3.0)),
            p=1.0,
        )
    if name == "RandomSunFlare":
        return A.RandomSunFlare(
            flare_roi=tuple(params.get("flare_roi", [0.0, 0.0, 1.0, 0.5])),
            src_radius=int(params.get("src_radius", 80)),
            src_color=tuple(params.get("src_color", [255, 255, 255])),
            angle_range=tuple(params.get("angle_range", [0.0, 1.0])),
            num_flare_circles_range=tuple(params.get("num_flare_circles_range", [1, 3])),
            method=params.get("method", "overlay"),
            p=1.0,
        )
    if name == "Illumination":
        return A.Illumination(
            mode=params.get("mode", "linear"),
            intensity_range=tuple(params.get("intensity_range", [0.01, 0.12])),
            effect_type=params.get("effect_type", "both"),
            angle_range=tuple(params.get("angle_range", [0, 360])),
            center_range=tuple(params.get("center_range", [0.25, 0.75])),
            sigma_range=tuple(params.get("sigma_range", [0.2, 0.6])),
            p=1.0,
        )
    raise ValueError(f"No Albumentations mapping for filter: {name}")


def pair(params: dict[str, Any], key: str, default: tuple[float, float]) -> tuple[float, float]:
    value = params.get(key, list(default))
    return float(value[0]), float(value[1])


def int_pair(params: dict[str, Any], key: str, default: tuple[int, int]) -> tuple[int, int]:
    value = params.get(key, list(default))
    return int(value[0]), int(value[1])


def clip(image: np.ndarray) -> np.ndarray:
    return np.clip(image, 0, 255).astype(np.uint8)


def hue_saturation_value(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV).astype(np.int16)
    hue = rng.integers(*inclusive_int_pair(params, "hue_shift_range", (-6, 6)))
    sat = rng.integers(*inclusive_int_pair(params, "sat_shift_range", (-18, 18)))
    val = rng.integers(*inclusive_int_pair(params, "val_shift_range", (-12, 12)))
    hsv[:, :, 0] = (hsv[:, :, 0] + hue) % 180
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] + sat, 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] + val, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)


def inclusive_int_pair(params: dict[str, Any], key: str, default: tuple[int, int]) -> tuple[int, int]:
    low, high = int_pair(params, key, default)
    return low, high + 1


def brightness_contrast(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    brightness = rng.uniform(*pair(params, "brightness_range", (-0.12, 0.12))) * 255.0
    contrast = 1.0 + rng.uniform(*pair(params, "contrast_range", (-0.12, 0.12)))
    return clip(image.astype(np.float32) * contrast + brightness)


def gaussian_blur(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    low, high = int_pair(params, "blur_limit", (3, 5))
    kernel = int(rng.integers(low, high + 1))
    if kernel % 2 == 0:
        kernel += 1
    sigma = rng.uniform(*pair(params, "sigma_limit", (0.0, 0.6)))
    return cv2.GaussianBlur(image, (kernel, kernel), sigmaX=sigma)


def additive_noise(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    std = rng.uniform(*pair(params, "std_range", (0.0, 0.06))) * 255.0
    mean = rng.uniform(*pair(params, "mean_range", (0.0, 0.0))) * 255.0
    noise = rng.normal(mean, std, image.shape)
    return clip(image.astype(np.float32) + noise)


def random_gamma(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    gamma = rng.uniform(*pair(params, "gamma_range", (90, 110))) / 100.0
    table = ((np.arange(256) / 255.0) ** (1.0 / max(gamma, 0.01)) * 255).astype(np.uint8)
    return cv2.LUT(image, table)


def planckian_jitter(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    temperature = rng.uniform(*pair(params, "temperature_range", (5000, 8500)))
    warmth = np.interp(temperature, [3000, 9000], [1.16, 0.92])
    cool = np.interp(temperature, [3000, 9000], [0.90, 1.10])
    factors = np.array([warmth, 1.0, cool], dtype=np.float32)
    return clip(image.astype(np.float32) * factors)


def salt_and_pepper(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    amount = rng.uniform(*pair(params, "amount_range", (0.0, 0.01)))
    salt_ratio = rng.uniform(*pair(params, "salt_vs_pepper_range", (0.45, 0.55)))
    mask = rng.random(image.shape[:2])
    out = image.copy()
    out[mask < amount * salt_ratio] = 255
    out[(mask >= amount * salt_ratio) & (mask < amount)] = 0
    return out


def motion_blur(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    low, high = int_pair(params, "blur_range", (3, 5))
    size = int(rng.integers(low, high + 1))
    if size % 2 == 0:
        size += 1
    angle = rng.uniform(*pair(params, "angle_range", (-12, 12)))
    kernel = np.zeros((size, size), dtype=np.float32)
    kernel[size // 2, :] = 1.0
    matrix = cv2.getRotationMatrix2D((size / 2 - 0.5, size / 2 - 0.5), angle, 1.0)
    kernel = cv2.warpAffine(kernel, matrix, (size, size))
    kernel /= max(kernel.sum(), 1e-6)
    return cv2.filter2D(image, -1, kernel)


def plasma_shadow(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    intensity = rng.uniform(*pair(params, "shadow_intensity_range", (0.1, 0.35)))
    plasma = smooth_noise(image.shape[:2], rng)
    factor = 1.0 - plasma[:, :, None] * intensity
    return clip(image.astype(np.float32) * factor)


def plasma_brightness_contrast(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    brightness = rng.uniform(*pair(params, "brightness_range", (-0.08, 0.08))) * 255
    contrast = rng.uniform(*pair(params, "contrast_range", (-0.08, 0.08)))
    plasma = smooth_noise(image.shape[:2], rng)[:, :, None]
    centered = image.astype(np.float32) - 127.5
    return clip(image.astype(np.float32) + plasma * brightness + centered * plasma * contrast)


def smooth_noise(shape: tuple[int, int], rng: np.random.Generator) -> np.ndarray:
    h, w = shape
    small = rng.random((max(2, h // 64), max(2, w // 64))).astype(np.float32)
    noise = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    noise = cv2.GaussianBlur(noise, (0, 0), sigmaX=max(h, w) / 32)
    return cv2.normalize(noise, None, 0.0, 1.0, cv2.NORM_MINMAX)


def random_sun_flare(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    h, w = image.shape[:2]
    roi = params.get("flare_roi", [0.0, 0.0, 1.0, 0.5])
    x = int(rng.uniform(roi[0], roi[2]) * w)
    y = int(rng.uniform(roi[1], roi[3]) * h)
    radius = int(params.get("src_radius", 80))
    color = np.array(params.get("src_color", [255, 255, 255]), dtype=np.float32)
    out = image.astype(np.float32)
    yy, xx = np.ogrid[:h, :w]
    dist = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
    glow = np.clip(1.0 - dist / max(radius * 4, 1), 0, 1)[:, :, None]
    out = out * (1 - glow * 0.35) + color * glow * 0.35
    return clip(out)


def illumination(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    h, w = image.shape[:2]
    intensity = rng.uniform(*pair(params, "intensity_range", (0.01, 0.12)))
    center_range = params.get("center_range", [0.25, 0.75])
    cx = rng.uniform(center_range[0], center_range[1]) * w
    cy = rng.uniform(center_range[0], center_range[1]) * h
    yy, xx = np.ogrid[:h, :w]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    mask = 1.0 - np.clip(dist / max(h, w), 0, 1)
    return clip(image.astype(np.float32) * (1.0 + mask[:, :, None] * intensity))


def atmospheric_fog(image: np.ndarray, params: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    density = rng.uniform(*pair(params, "density_range", (0.05, 0.15)))
    fog_color = np.array(params.get("fog_color", [255, 255, 255]), dtype=np.float32)
    h = image.shape[0]
    gradient = np.linspace(0.25, 1.0, h, dtype=np.float32)[:, None, None]
    alpha = gradient * density
    return clip(image.astype(np.float32) * (1 - alpha) + fog_color * alpha)
