from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .assets import AssetCatalog, AssetRecord
from .models import BackgroundRecipe, RecipeCatalog, RecipeNode


class BackgroundSynthesisError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackgroundSample:
    image: np.ndarray
    recipe_id: str
    recipe_version: int
    graph_hash: str
    source_assets: tuple[dict[str, Any], ...]
    sampled_parameters: dict[str, dict[str, Any]]
    node_timings_ns: dict[str, int]
    qa: dict[str, Any]
    warnings: tuple[str, ...]


def _sample_range(value: Any, rng: np.random.Generator, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return float(rng.uniform(float(value[0]), float(value[1])))


def _load_rgb_float(asset: AssetRecord) -> np.ndarray:
    with Image.open(asset.path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _resize_cover_crop(image: np.ndarray, size: tuple[int, int], rng: np.random.Generator) -> np.ndarray:
    target_w, target_h = size
    height, width = image.shape[:2]
    scale = max(target_w / width, target_h / height)
    resized_w = max(target_w, int(np.ceil(width * scale)))
    resized_h = max(target_h, int(np.ceil(height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=interpolation)
    max_x = resized_w - target_w
    max_y = resized_h - target_h
    x = int(rng.integers(0, max_x + 1)) if max_x else 0
    y = int(rng.integers(0, max_y + 1)) if max_y else 0
    return resized[y : y + target_h, x : x + target_w].copy()


def _rgb_to_space(image: np.ndarray, color_space: str) -> np.ndarray:
    normalized = color_space.lower()
    if normalized == "rgb":
        return image
    if normalized == "lab":
        return cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2LAB)
    if normalized == "hsv":
        return cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2HSV)
    raise BackgroundSynthesisError(f"Unsupported color space: {color_space}")


def _space_to_rgb(image: np.ndarray, color_space: str) -> np.ndarray:
    normalized = color_space.lower()
    if normalized == "rgb":
        return image
    if normalized == "lab":
        return cv2.cvtColor(image.astype(np.float32), cv2.COLOR_LAB2RGB)
    if normalized == "hsv":
        return cv2.cvtColor(image.astype(np.float32), cv2.COLOR_HSV2RGB)
    raise BackgroundSynthesisError(f"Unsupported color space: {color_space}")


def _normalize_channel(channel: np.ndarray) -> np.ndarray:
    low = float(np.percentile(channel, 1))
    high = float(np.percentile(channel, 99))
    if high - low < 1e-8:
        return np.zeros_like(channel, dtype=np.float32)
    return np.clip((channel.astype(np.float32) - low) / (high - low), 0.0, 1.0)


def _palette_transfer(image: np.ndarray, palette: np.ndarray, strength: float) -> np.ndarray:
    source_lab = cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2LAB)
    palette_lab = cv2.cvtColor(palette.astype(np.float32), cv2.COLOR_RGB2LAB)
    source_flat = source_lab.reshape(-1, 3)
    palette_flat = palette_lab.reshape(-1, 3)
    source_mean = source_flat.mean(axis=0)
    source_std = np.maximum(source_flat.std(axis=0), 1e-5)
    palette_mean = palette_flat.mean(axis=0)
    palette_std = np.maximum(palette_flat.std(axis=0), 1e-5)
    transferred = (source_lab - source_mean) * (palette_std / source_std) + palette_mean
    mixed = source_lab * (1.0 - strength) + transferred * strength
    return np.clip(cv2.cvtColor(mixed.astype(np.float32), cv2.COLOR_LAB2RGB), 0.0, 1.0)


def _normalize_mask(mask: np.ndarray, params: dict[str, Any], size: tuple[int, int]) -> np.ndarray:
    percentiles = params.get("percentiles", [5, 95])
    low, high = np.percentile(mask, [float(percentiles[0]), float(percentiles[1])])
    if high - low < 1e-8:
        normalized = np.full(mask.shape, 0.5, dtype=np.float32)
    else:
        normalized = np.clip((mask.astype(np.float32) - low) / (high - low), 0.0, 1.0)
    if params.get("invert", False):
        normalized = 1.0 - normalized
    gamma = float(params.get("gamma", 1.0))
    normalized = np.power(normalized, gamma)
    curve = str(params.get("curve", "linear"))
    if curve == "smoothstep":
        normalized = normalized * normalized * (3.0 - 2.0 * normalized)
    elif curve != "linear":
        raise BackgroundSynthesisError(f"Unsupported mask curve: {curve}")
    if "threshold" in params:
        normalized = (normalized >= float(params["threshold"])).astype(np.float32)
    blur_fraction = float(params.get("blur_fraction", 0.0))
    if blur_fraction > 0:
        sigma = max(0.5, blur_fraction * max(size))
        normalized = cv2.GaussianBlur(normalized, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return np.clip(normalized, 0.0, 1.0)


def _multiband_blend(first: np.ndarray, second: np.ndarray, mask: np.ndarray, levels: int) -> np.ndarray:
    max_levels = max(1, int(np.floor(np.log2(max(2, min(first.shape[:2]))))) - 3)
    levels = max(1, min(levels, max_levels))
    gp_first = [first.astype(np.float32)]
    gp_second = [second.astype(np.float32)]
    gp_mask = [mask.astype(np.float32)]
    for _ in range(levels):
        gp_first.append(cv2.pyrDown(gp_first[-1]))
        gp_second.append(cv2.pyrDown(gp_second[-1]))
        gp_mask.append(cv2.pyrDown(gp_mask[-1]))
    lp_first = [gp_first[-1]]
    lp_second = [gp_second[-1]]
    for index in range(levels, 0, -1):
        size = (gp_first[index - 1].shape[1], gp_first[index - 1].shape[0])
        lp_first.append(gp_first[index - 1] - cv2.pyrUp(gp_first[index], dstsize=size))
        lp_second.append(gp_second[index - 1] - cv2.pyrUp(gp_second[index], dstsize=size))
    blended_levels: list[np.ndarray] = []
    for first_level, second_level, mask_level in zip(lp_first, lp_second, reversed(gp_mask)):
        weight = mask_level[:, :, None]
        blended_levels.append(first_level * weight + second_level * (1.0 - weight))
    result = blended_levels[0]
    for level in blended_levels[1:]:
        result = cv2.pyrUp(result, dstsize=(level.shape[1], level.shape[0])) + level
    return np.clip(result, 0.0, 1.0)


def _displace(
    image: np.ndarray,
    map_x_source: np.ndarray,
    map_y_source: np.ndarray,
    amplitude: float,
    blur_fraction: float,
) -> tuple[np.ndarray, dict[str, float]]:
    if not 0.0 <= amplitude <= 0.1:
        raise BackgroundSynthesisError("Displacement amplitude_fraction must be between 0 and 0.1")
    height, width = image.shape[:2]
    sigma = max(0.5, blur_fraction * max(width, height))
    dx = cv2.GaussianBlur(_normalize_channel(map_x_source), (0, 0), sigmaX=sigma) * 2.0 - 1.0
    dy = cv2.GaussianBlur(_normalize_channel(map_y_source), (0, 0), sigmaX=sigma) * 2.0 - 1.0
    max_displacement = amplitude * min(width, height)
    dx *= max_displacement
    dy *= max_displacement
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    map_x = grid_x + dx.astype(np.float32)
    map_y = grid_y + dy.astype(np.float32)
    grad_x_x = np.gradient(map_x, axis=1)
    grad_x_y = np.gradient(map_x, axis=0)
    grad_y_x = np.gradient(map_y, axis=1)
    grad_y_y = np.gradient(map_y, axis=0)
    jacobian = grad_x_x * grad_y_y - grad_x_y * grad_y_x
    min_jacobian = float(np.min(jacobian))
    if not np.isfinite(map_x).all() or not np.isfinite(map_y).all() or min_jacobian <= 0.05:
        raise BackgroundSynthesisError(f"Displacement map folds or is invalid (min Jacobian {min_jacobian:.4f})")
    warped = cv2.remap(
        image,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return warped, {"amplitude_fraction": amplitude, "min_jacobian": min_jacobian}


def _qa(image: np.ndarray) -> tuple[dict[str, Any], tuple[str, ...]]:
    finite = bool(np.isfinite(image).all())
    if not finite:
        raise BackgroundSynthesisError("Background contains NaN or infinite values")
    clipped = np.logical_or(image <= 1e-5, image >= 1.0 - 1e-5)
    clipping_fraction = float(clipped.mean())
    luminance = cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2GRAY)
    luminance_std = float(luminance.std())
    if luminance_std < 0.003:
        raise BackgroundSynthesisError("Background is near-constant")
    if clipping_fraction > 0.98:
        raise BackgroundSynthesisError("Background is severely clipped")
    edge_horizontal = float(np.mean(np.abs(image[:, 0] - image[:, -1])))
    edge_vertical = float(np.mean(np.abs(image[0] - image[-1])))
    lab = cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2LAB)
    hsv = cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2HSV)
    reduced = cv2.resize(luminance, (max(1, luminance.shape[1] // 4), max(1, luminance.shape[0] // 4)))
    low_frequency = float(cv2.resize(reduced, (luminance.shape[1], luminance.shape[0])).std())
    high_frequency = float(cv2.Laplacian(luminance, cv2.CV_32F).std())
    seam_score = (edge_horizontal + edge_vertical) / 2.0
    qa = {
        "finite": finite,
        "uncovered_fraction": 0.0,
        "clipping_fraction": clipping_fraction,
        "luminance_std": luminance_std,
        "chroma_std": float(np.mean([lab[:, :, 1].std(), lab[:, :, 2].std()])),
        "saturation_mean": float(hsv[:, :, 1].mean()),
        "frequency_energy_low": low_frequency,
        "frequency_energy_high": high_frequency,
        "edge_seam_score": seam_score,
    }
    warnings: list[str] = []
    if luminance_std < 0.025:
        warnings.append("low_luminance_spread")
    if clipping_fraction > 0.20:
        warnings.append("elevated_clipping")
    if seam_score > 0.12:
        warnings.append("high_edge_seam")
    return qa, tuple(warnings)


def _perceptual_hash(image: np.ndarray) -> int:
    gray = cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2GRAY)
    values = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    bits = (values >= values.mean()).reshape(-1)
    return int("".join("1" if bit else "0" for bit in bits), 2)


class BackgroundSynthesizer:
    def __init__(
        self,
        catalog: AssetCatalog,
        recipes: RecipeCatalog,
        group_weights: dict[str, float] | None = None,
        asset_weights: dict[str, float] | None = None,
    ) -> None:
        self.catalog = catalog
        self.recipes = recipes
        self.group_weights = group_weights or {}
        self.asset_weights = asset_weights or {}

    def synthesize(
        self,
        recipe_id: str,
        size: tuple[int, int],
        rng: np.random.Generator,
    ) -> BackgroundSample:
        if recipe_id not in self.recipes.recipes:
            raise BackgroundSynthesisError(f"Unknown background recipe: {recipe_id}")
        recipe = self.recipes.recipes[recipe_id]
        graph_hash = hashlib.sha256(
            json.dumps(recipe.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        values: dict[str, Any] = {}
        timings: dict[str, int] = {}
        sampled: dict[str, dict[str, Any]] = {}
        sources: list[dict[str, Any]] = []
        anchor_group: str | None = None

        for node in recipe.nodes:
            started = perf_counter_ns()
            node_sampled: dict[str, Any] = {}
            try:
                value = self._execute_node(node, recipe, values, size, rng, anchor_group, node_sampled)
            except BackgroundSynthesisError:
                raise
            except Exception as exc:
                raise BackgroundSynthesisError(f"Recipe {recipe_id} node {node.id} failed: {exc}") from exc
            finally:
                timings[node.id] = perf_counter_ns() - started
            values[node.id] = value
            sampled[node.id] = node_sampled
            if isinstance(value, AssetRecord):
                if anchor_group is None:
                    anchor_group = value.group
                sources.append(
                    {
                        "node": node.id,
                        "logical_path": value.logical_path,
                        "content_hash": value.content_hash,
                        "perceptual_hash": value.perceptual_hash,
                        "group": value.group,
                        "reused": any(item["content_hash"] == value.content_hash for item in sources),
                    }
                )

        output = values[recipe.output]
        if isinstance(output, AssetRecord):
            output = _resize_cover_crop(_load_rgb_float(output), size, rng)
        if not isinstance(output, np.ndarray) or output.ndim != 3 or output.shape[2] != 3:
            raise BackgroundSynthesisError(f"Recipe {recipe_id} output must be an RGB image")
        if output.shape[:2] != (size[1], size[0]):
            output = cv2.resize(output, size, interpolation=cv2.INTER_LINEAR)
        output = np.clip(output.astype(np.float32), 0.0, 1.0)
        qa, warnings = _qa(output)
        output_hash = _perceptual_hash(output)
        nearest_source_similarity = max(
            (1.0 - ((output_hash ^ int(source["perceptual_hash"], 16)).bit_count() / 64.0) for source in sources),
            default=0.0,
        )
        qa["nearest_source_similarity"] = nearest_source_similarity
        if nearest_source_similarity >= 0.98:
            warnings = (*warnings, "near_duplicate_source")
        groups = {str(source["group"]) for source in sources}
        qa["cross_group"] = len(groups) > 1
        qa["source_reuse"] = any(bool(source["reused"]) for source in sources)
        if recipe.tileable and float(qa["edge_seam_score"]) > 0.12:
            raise BackgroundSynthesisError("Tileable recipe output failed edge-seam validation")
        return BackgroundSample(
            image=np.round(output * 255.0).astype(np.uint8),
            recipe_id=recipe_id,
            recipe_version=recipe.version,
            graph_hash=graph_hash,
            source_assets=tuple(sources),
            sampled_parameters=sampled,
            node_timings_ns=timings,
            qa=qa,
            warnings=warnings,
        )

    def _execute_node(
        self,
        node: RecipeNode,
        recipe: BackgroundRecipe,
        values: dict[str, Any],
        size: tuple[int, int],
        rng: np.random.Generator,
        anchor_group: str | None,
        sampled: dict[str, Any],
    ) -> Any:
        inputs = {name: values[reference] for name, reference in node.inputs.items()}
        if node.op == "sample_asset":
            requested_group = node.params.get("group")
            role = str(node.params.get("role", node.id))
            same_group_node = node.params.get("same_group_as")
            if same_group_node:
                requested_group = values[str(same_group_node)].group
            elif anchor_group and requested_group is None:
                requested_group = anchor_group
            if anchor_group and requested_group and requested_group != anchor_group:
                allowed = {tuple(pair) for pair in recipe.allowed_cross_group_pairs}
                if (anchor_group, str(requested_group)) not in allowed and (str(requested_group), anchor_group) not in allowed:
                    raise BackgroundSynthesisError(
                        f"Cross-group combination {anchor_group!r}/{requested_group!r} is not allow-listed"
                    )
            candidates = [asset for asset in self.catalog.backgrounds if not requested_group or asset.group == requested_group]
            candidates = [asset for asset in candidates if not asset.approved_roles or role in asset.approved_roles]
            if not candidates:
                raise BackgroundSynthesisError(f"No background candidates for group {requested_group}")
            distinct_references = [values[name] for name in node.params.get("distinct_from", []) if name in values]
            distinct_hashes = {asset.content_hash for asset in distinct_references if isinstance(asset, AssetRecord)}
            distinct_candidates = [asset for asset in candidates if asset.content_hash not in distinct_hashes]
            if distinct_candidates:
                candidates = distinct_candidates
            weights = np.array(
                [
                    self.group_weights.get(asset.group, 0.0 if self.group_weights else 1.0)
                    * self.asset_weights.get(asset.logical_path, 1.0)
                    for asset in candidates
                ],
                dtype=np.float64,
            )
            if weights.sum() <= 0:
                raise BackgroundSynthesisError("Background candidate weights sum to zero")
            weights /= weights.sum()
            chosen = candidates[int(rng.choice(len(candidates), p=weights))]
            sampled.update({"group": chosen.group, "logical_path": chosen.logical_path, "role": role})
            return chosen
        if node.op == "resize_crop":
            source = inputs["image"]
            image = _load_rgb_float(source) if isinstance(source, AssetRecord) else source
            return _resize_cover_crop(image, size, rng)
        if node.op == "colorspace_convert":
            image = inputs["image"]
            from_space = str(node.params.get("from", "RGB"))
            to_space = str(node.params.get("to", "RGB"))
            rgb = _space_to_rgb(image, from_space)
            return _rgb_to_space(rgb, to_space)
        if node.op == "channel_extract":
            image = inputs["image"]
            color_space = str(node.params.get("color_space", "RGB"))
            channel = int(node.params.get("channel", 0))
            converted = _rgb_to_space(image, color_space)
            sampled.update({"color_space": color_space, "channel": channel})
            return _normalize_channel(converted[:, :, channel])
        if node.op == "channel_compose":
            color_space = str(node.params.get("color_space", "RGB"))
            channels = [inputs[name] for name in ("channel_0", "channel_1", "channel_2")]
            composed = np.dstack(channels).astype(np.float32)
            if color_space.lower() == "lab":
                composed[:, :, 0] *= 100.0
                composed[:, :, 1:] = composed[:, :, 1:] * 255.0 - 128.0
            elif color_space.lower() == "hsv":
                composed[:, :, 0] *= 360.0
            return np.clip(_space_to_rgb(composed, color_space), 0.0, 1.0)
        if node.op == "palette_transfer":
            strength = _sample_range(node.params.get("strength"), rng, 0.5)
            sampled["strength"] = strength
            return _palette_transfer(inputs["image"], inputs["palette"], strength)
        if node.op == "mask_normalize":
            return _normalize_mask(inputs["mask"], node.params, size)
        if node.op == "linear_blend":
            weight = inputs["mask"][:, :, None]
            return np.clip(inputs["first"] * weight + inputs["second"] * (1.0 - weight), 0.0, 1.0)
        if node.op == "multiband_blend":
            levels = int(node.params.get("levels", 5))
            sampled["levels"] = levels
            return _multiband_blend(inputs["first"], inputs["second"], inputs["mask"], levels)
        if node.op == "displace":
            amplitude = _sample_range(node.params.get("amplitude_fraction"), rng, 0.01)
            blur_fraction = float(node.params.get("blur_fraction", 0.02))
            result, details = _displace(inputs["image"], inputs["map_x"], inputs["map_y"], amplitude, blur_fraction)
            sampled.update(details)
            return result
        raise BackgroundSynthesisError(f"Unsupported recipe operation: {node.op}")
