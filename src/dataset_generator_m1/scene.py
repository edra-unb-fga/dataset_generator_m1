from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .assets import AssetCatalog, AssetRecord
from .backgrounds import BackgroundSample
from .filters import apply_pipeline
from .imaging import read_rgba, resize_rgba, rotate_rgba, visible_bbox
from .models import ResolvedProfile


BBox = tuple[int, int, int, int]


class SceneRejected(RuntimeError):
    pass


def derive_seed(seed: int, slot: int, candidate_attempt: int, stream_name: str) -> int:
    payload = f"{seed}:{slot}:{candidate_attempt}:{stream_name}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


@dataclass(frozen=True)
class PlannedInstance:
    asset: AssetRecord
    center: tuple[float, float]
    width_fraction: float
    angle_degrees: float

    def signature(self) -> dict[str, Any]:
        return {
            "asset": self.asset.content_hash,
            "center": [round(value, 9) for value in self.center],
            "width_fraction": round(self.width_fraction, 9),
            "angle_degrees": round(self.angle_degrees, 9),
        }


@dataclass(frozen=True)
class ScenePlan:
    slot: int
    candidate_attempt: int
    canvas_size: tuple[int, int]
    camera_rect: tuple[float, float, float, float]
    scene_to_output: np.ndarray
    perspective_quad: np.ndarray
    recipe_id: str
    instances: tuple[PlannedInstance, ...]
    attempted_instances: int
    planning_rejections: tuple[dict[str, Any], ...]
    intentional_negative: bool
    appearance_seed: int

    def geometry_signature(self) -> str:
        payload = {
            "slot": self.slot,
            "attempt": self.candidate_attempt,
            "canvas_size": self.canvas_size,
            "camera_rect": [round(value, 9) for value in self.camera_rect],
            "scene_to_output": np.round(self.scene_to_output, 9).tolist(),
            "instances": [instance.signature() for instance in self.instances],
            "negative": self.intentional_negative,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Annotation:
    class_id: int
    class_name: str
    bbox: BBox
    normalized_bbox: tuple[float, float, float, float]
    visible_bbox_fraction: float
    source_asset: str
    source_group: str
    asset_to_scene: np.ndarray
    asset_to_output: np.ndarray


@dataclass(frozen=True)
class RenderedScene:
    image: np.ndarray
    annotations: tuple[Annotation, ...]
    instance_masks: tuple[np.ndarray, ...]
    scene_to_output: np.ndarray
    coverage_fraction: float
    rejected_instances: tuple[dict[str, Any], ...]


def _weighted_choice(
    records: tuple[AssetRecord, ...],
    rng: np.random.Generator,
    group_weights: dict[str, float],
    asset_weights: dict[str, float],
) -> AssetRecord:
    candidates = list(records)
    if group_weights:
        present = {record.group for record in records}
        unknown = set(group_weights) - present
        if unknown:
            raise ValueError(f"Unknown foreground groups in weights: {sorted(unknown)}")
        candidates = [record for record in records if group_weights.get(record.group, 0.0) > 0]
        weights = np.array(
            [group_weights.get(record.group, 0.0) * asset_weights.get(record.logical_path, 1.0) for record in candidates],
            dtype=np.float64,
        )
    else:
        weights = np.array([asset_weights.get(record.logical_path, 1.0) for record in candidates], dtype=np.float64)
    if not candidates or weights.sum() <= 0:
        raise ValueError("No foreground assets have positive sampling weight")
    weights /= weights.sum()
    return candidates[int(rng.choice(len(candidates), p=weights))]


def _shoelace_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


class ScenePlanner:
    def __init__(self, resolved: ResolvedProfile, catalog: AssetCatalog) -> None:
        self.resolved = resolved
        self.profile = resolved.profile
        self.catalog = catalog

    def plan(self, slot: int, candidate_attempt: int) -> ScenePlan:
        seed = self.profile.run.seed
        geometry_rng = np.random.default_rng(derive_seed(seed, slot, candidate_attempt, "geometry"))
        foreground_rng = np.random.default_rng(derive_seed(seed, slot, candidate_attempt, "foreground-assets"))
        background_rng = np.random.default_rng(derive_seed(seed, slot, candidate_attempt, "background-recipe"))
        negative_rng = np.random.default_rng(derive_seed(seed, slot, candidate_attempt, "negative"))
        appearance_seed = derive_seed(seed, slot, candidate_attempt, "appearance")

        out_w, out_h = self.profile.output.image_size
        scene_w = max(out_w + 2, int(np.ceil(out_w * self.profile.scene.canvas_scale)))
        scene_h = max(out_h + 2, int(np.ceil(out_h * self.profile.scene.canvas_scale)))
        crop_scale = float(geometry_rng.uniform(*self.profile.scene.camera.crop_scale))
        camera_w = min(scene_w * 0.9, out_w * crop_scale)
        camera_h = min(scene_h * 0.9, out_h * crop_scale)
        jitter_x = float(geometry_rng.uniform(*self.profile.scene.camera.center_jitter_x)) * camera_w
        jitter_y = float(geometry_rng.uniform(*self.profile.scene.camera.center_jitter_y)) * camera_h
        camera_x = np.clip((scene_w - camera_w) / 2.0 + jitter_x, 1.0, scene_w - camera_w - 1.0)
        camera_y = np.clip((scene_h - camera_h) / 2.0 + jitter_y, 1.0, scene_h - camera_h - 1.0)

        src = np.float32([[0, 0], [scene_w, 0], [scene_w, scene_h], [0, scene_h]])
        dst = src.copy()
        perspective = self.profile.scene.perspective
        if geometry_rng.random() <= perspective.probability:
            dst[:, 0] += geometry_rng.uniform(*perspective.corner_offset_x, size=4) * camera_w
            dst[:, 1] += geometry_rng.uniform(*perspective.corner_offset_y, size=4) * camera_h
        if not cv2.isContourConvex(dst.reshape(-1, 1, 2)):
            raise SceneRejected("sampled perspective quadrilateral is not convex")
        area_fraction = _shoelace_area(dst) / float(scene_w * scene_h)
        if area_fraction < perspective.min_area_fraction:
            raise SceneRejected(f"sampled perspective area fraction {area_fraction:.4f} is below minimum")
        scene_homography = cv2.getPerspectiveTransform(src, dst)
        crop_transform = np.array(
            [[out_w / camera_w, 0.0, -camera_x * out_w / camera_w], [0.0, out_h / camera_h, -camera_y * out_h / camera_h], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        scene_to_output = crop_transform @ scene_homography

        weights = self.profile.background_synthesis.recipe_weights
        recipe_names = list(weights)
        recipe_probabilities = np.array([weights[name] for name in recipe_names], dtype=np.float64)
        recipe_probabilities /= recipe_probabilities.sum()
        recipe_id = str(background_rng.choice(recipe_names, p=recipe_probabilities))

        intentional_negative = negative_rng.random() < self.profile.run.negative_fraction
        instances: list[PlannedInstance] = []
        planning_rejections: list[dict[str, Any]] = []
        occupied: list[tuple[float, float, float, float]] = []
        attempted_instances = 0
        if not intentional_negative:
            low, high = self.profile.sampling.instances_per_image
            count = int(geometry_rng.integers(low, high + 1))
            attempted_instances = count
            for _ in range(count):
                foreground_source = self.profile.assets.foregrounds
                asset = _weighted_choice(
                    self.catalog.foregrounds,
                    foreground_rng,
                    foreground_source.group_weights,
                    foreground_source.asset_weights,
                )
                width_fraction = float(geometry_rng.uniform(*self.profile.sampling.foreground_size))
                rotation = self.resolved.family.rotation
                angle = float(geometry_rng.uniform(*rotation.angle_degrees)) if geometry_rng.random() <= rotation.probability else 0.0
                estimated_w = camera_w * width_fraction
                aspect = asset.height / max(asset.width, 1)
                estimated_h = estimated_w * aspect
                radius_w = np.hypot(estimated_w, estimated_h) / 2.0
                radius_h = radius_w
                spacing_x = self.profile.sampling.bbox_spacing * camera_w
                spacing_y = self.profile.sampling.bbox_spacing * camera_h
                placed = False
                for _placement_attempt in range(self.profile.sampling.placement_attempts):
                    margin_x = radius_w * 0.15
                    margin_y = radius_h * 0.15
                    center_x = float(geometry_rng.uniform(camera_x - margin_x, camera_x + camera_w + margin_x))
                    center_y = float(geometry_rng.uniform(camera_y - margin_y, camera_y + camera_h + margin_y))
                    bbox = (
                        center_x - radius_w - spacing_x,
                        center_y - radius_h - spacing_y,
                        center_x + radius_w + spacing_x,
                        center_y + radius_h + spacing_y,
                    )
                    if any(not (bbox[2] <= other[0] or other[2] <= bbox[0] or bbox[3] <= other[1] or other[3] <= bbox[1]) for other in occupied):
                        continue
                    occupied.append(bbox)
                    instances.append(PlannedInstance(asset, (center_x, center_y), width_fraction, angle))
                    placed = True
                    break
                if not placed:
                    planning_rejections.append({"source": asset.logical_path, "reason": "placement_attempts_exhausted"})

        return ScenePlan(
            slot=slot,
            candidate_attempt=candidate_attempt,
            canvas_size=(scene_w, scene_h),
            camera_rect=(float(camera_x), float(camera_y), float(camera_w), float(camera_h)),
            scene_to_output=scene_to_output,
            perspective_quad=dst.astype(np.float64),
            recipe_id=recipe_id,
            instances=tuple(instances),
            attempted_instances=attempted_instances,
            planning_rejections=tuple(planning_rejections),
            intentional_negative=intentional_negative,
            appearance_seed=appearance_seed,
        )


def _bbox_from_mask(mask: np.ndarray, threshold: int = 8) -> BBox | None:
    ys, xs = np.where(mask > threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def _transform_bbox(matrix: np.ndarray, bbox: BBox) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    points = np.array([[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(points, matrix.astype(np.float64))[0]
    return (
        float(transformed[:, 0].min()),
        float(transformed[:, 1].min()),
        float(transformed[:, 0].max()),
        float(transformed[:, 1].max()),
    )


class SceneRenderer:
    def __init__(self, resolved: ResolvedProfile) -> None:
        self.resolved = resolved
        self.profile = resolved.profile

    def render(self, plan: ScenePlan, background: BackgroundSample) -> RenderedScene:
        out_w, out_h = self.profile.output.image_size
        if background.image.shape[:2] != (plan.canvas_size[1], plan.canvas_size[0]):
            raise ValueError("Background sample size does not match scene canvas")
        appearance_rng = np.random.default_rng(plan.appearance_seed)
        background_image = apply_pipeline(background.image, self.profile.appearance.background, appearance_rng)
        affine = self.profile.scene.background_affine
        angle = float(appearance_rng.uniform(*affine.rotation_degrees))
        scale = float(appearance_rng.uniform(*affine.scale))
        tx = float(appearance_rng.uniform(*affine.translation_x)) * plan.canvas_size[0]
        ty = float(appearance_rng.uniform(*affine.translation_y)) * plan.canvas_size[1]
        affine_matrix = cv2.getRotationMatrix2D((plan.canvas_size[0] / 2, plan.canvas_size[1] / 2), angle, scale)
        affine_matrix[:, 2] += (tx, ty)
        background_image = cv2.warpAffine(
            background_image,
            affine_matrix,
            plan.canvas_size,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        rendered = cv2.warpPerspective(
            background_image,
            plan.scene_to_output,
            (out_w, out_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        coverage_source = np.full((plan.canvas_size[1], plan.canvas_size[0]), 255, dtype=np.uint8)
        coverage = cv2.warpPerspective(
            coverage_source,
            plan.scene_to_output,
            (out_w, out_h),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        coverage_fraction = float(np.mean(coverage == 255))
        if coverage_fraction < 1.0:
            raise SceneRejected(f"background coverage incomplete: {coverage_fraction:.6f}")

        annotations: list[Annotation] = []
        masks: list[np.ndarray] = []
        rejected: list[dict[str, Any]] = []
        camera_w = plan.camera_rect[2]
        for index, instance in enumerate(plan.instances):
            instance_rng = np.random.default_rng(derive_seed(plan.appearance_seed, index, 0, "foreground-appearance"))
            rgba = read_rgba(instance.asset.path)
            rgba = apply_pipeline(rgba, self.profile.appearance.foreground, instance_rng, preserve_alpha=True)
            rgba = rotate_rgba(rgba, instance.angle_degrees, self.resolved.family.rotation.mode)
            target_width = max(1, int(round(camera_w * instance.width_fraction)))
            rgba = resize_rgba(rgba, target_width)
            local_bbox = visible_bbox(rgba)
            if local_bbox is None:
                rejected.append({"source": instance.asset.logical_path, "reason": "empty_alpha"})
                continue
            height, width = rgba.shape[:2]
            top_left_x = instance.center[0] - width / 2.0
            top_left_y = instance.center[1] - height / 2.0
            asset_to_scene = np.array([[1.0, 0.0, top_left_x], [0.0, 1.0, top_left_y], [0.0, 0.0, 1.0]], dtype=np.float64)
            asset_to_output = plan.scene_to_output @ asset_to_scene
            warped_rgb = cv2.warpPerspective(
                rgba[:, :, :3],
                asset_to_output,
                (out_w, out_h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
            warped_alpha = cv2.warpPerspective(
                rgba[:, :, 3],
                asset_to_output,
                (out_w, out_h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            clipped_bbox = _bbox_from_mask(warped_alpha)
            if clipped_bbox is None:
                rejected.append({"source": instance.asset.logical_path, "reason": "outside_frame"})
                continue
            full_bbox = _transform_bbox(asset_to_output, local_bbox)
            full_area = max(1e-9, (full_bbox[2] - full_bbox[0]) * (full_bbox[3] - full_bbox[1]))
            clipped_area = float((clipped_bbox[2] - clipped_bbox[0]) * (clipped_bbox[3] - clipped_bbox[1]))
            visible_fraction = min(1.0, clipped_area / full_area)
            if visible_fraction < self.profile.sampling.min_visible_bbox_fraction:
                rejected.append(
                    {
                        "source": instance.asset.logical_path,
                        "reason": "visible_bbox_fraction",
                        "value": visible_fraction,
                    }
                )
                continue
            alpha = warped_alpha[:, :, None].astype(np.float32) / 255.0
            rendered = np.clip(warped_rgb.astype(np.float32) * alpha + rendered.astype(np.float32) * (1.0 - alpha), 0, 255).astype(np.uint8)
            x1, y1, x2, y2 = clipped_bbox
            normalized_bbox = (
                ((x1 + x2) / 2.0) / out_w,
                ((y1 + y2) / 2.0) / out_h,
                (x2 - x1) / out_w,
                (y2 - y1) / out_h,
            )
            annotations.append(
                Annotation(
                    class_id=int(instance.asset.class_id),
                    class_name=str(instance.asset.class_name),
                    bbox=clipped_bbox,
                    normalized_bbox=normalized_bbox,
                    visible_bbox_fraction=visible_fraction,
                    source_asset=instance.asset.logical_path,
                    source_group=instance.asset.group,
                    asset_to_scene=asset_to_scene,
                    asset_to_output=asset_to_output,
                )
            )
            masks.append(warped_alpha)

        if not annotations and not plan.intentional_negative:
            raise SceneRejected("candidate has no accepted foreground annotations")
        rendered = apply_pipeline(rendered, self.profile.appearance.final, appearance_rng)
        return RenderedScene(
            image=rendered,
            annotations=tuple(annotations),
            instance_masks=tuple(masks),
            scene_to_output=plan.scene_to_output,
            coverage_fraction=coverage_fraction,
            rejected_instances=tuple(rejected),
        )
