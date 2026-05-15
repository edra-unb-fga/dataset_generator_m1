from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from .assets import discover_foregrounds, discover_images
from .config import GeneratorConfig
from .filters import apply_filter_groups
from .imaging import (
    alpha_composite,
    apply_perspective,
    apply_rgb_affine,
    center_crop,
    clip_bbox,
    expand_rect,
    read_rgb,
    read_rgba,
    rects_intersect,
    resize_rgba,
    rotate_rgba,
    tile_background,
    visible_bbox,
    write_image,
)
from .types import Asset, BBox, ForegroundInstance, PerspectiveSample, PlacedInstance


class DatasetGenerator:
    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.data = config.data
        self.rng = np.random.default_rng(int(self.data["seed"]))
        self.backgrounds = discover_images(
            self.data["paths"]["backgrounds_dir"],
            recursive=bool(self.data["paths"].get("recursive_backgrounds", True)),
        )
        if not self.backgrounds:
            raise FileNotFoundError(f"No background images found in {self.data['paths']['backgrounds_dir']}")
        self.foregrounds, self.class_names = discover_foregrounds(
            self.data["paths"]["foregrounds_dir"],
            self.data["dataset_type"],
        )

    def generate(self) -> dict[str, Any]:
        output_dir = self.config.output_dir
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        debug_dir = output_dir / str(self.data["debug_dir"])
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)
        if self.config.debug_count:
            debug_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "config": self.data,
            "config_path": str(self.config.config_path) if self.config.config_path else None,
            "classes": self.class_names,
            "samples": [],
            "skips": [],
        }

        generated = 0
        attempts = 0
        max_attempts = max(self.config.num_images * 5, self.config.num_images + 10)
        while generated < self.config.num_images and attempts < max_attempts:
            attempts += 1
            sample_rng = np.random.default_rng(int(self.rng.integers(0, 2**31 - 1)))
            try:
                record = self.generate_one(generated, images_dir, labels_dir, debug_dir, sample_rng)
            except Exception as exc:
                manifest["skips"].append({"index": generated, "reason": str(exc)})
                continue
            if record is None:
                manifest["skips"].append({"index": generated, "reason": "no_valid_annotations"})
                continue
            manifest["samples"].append(record)
            generated += 1

        if generated < self.config.num_images:
            recent_reasons = manifest["skips"][-5:]
            raise RuntimeError(
                f"Generated {generated}/{self.config.num_images} images before retry budget was exhausted. "
                f"Recent skips: {recent_reasons}"
            )

        if self.data["output"].get("write_data_yaml", True):
            self.write_data_yaml(output_dir)
        if self.data["output"].get("write_manifest", True):
            (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def generate_one(
        self,
        index: int,
        images_dir: Path,
        labels_dir: Path,
        debug_dir: Path,
        rng: np.random.Generator,
    ) -> dict[str, Any] | None:
        out_w, out_h = self.config.image_size
        crop_size = self.sample_crop_size(rng)
        work_size = (max(out_w, crop_size) * 3, max(out_h, crop_size) * 3)
        perspective = self.sample_perspective(work_size, rng)

        background_path = Path(rng.choice(self.backgrounds))
        background = self.generate_background(background_path, work_size, perspective, rng)
        canvas, crop_origin = center_crop(background, (crop_size, crop_size))

        instances = self.sample_foreground_instances(rng)
        placed: list[PlacedInstance] = []
        occupied: list[BBox] = []
        for asset in instances:
            foreground = self.generate_foreground(asset, perspective, rng)
            scaled = self.scale_foreground(foreground, out_w, rng)
            placement = self.place_foreground(canvas, scaled, occupied, rng)
            if placement is None:
                continue
            x, y, bbox, attempts = placement
            alpha_composite(canvas, scaled.image, x, y)
            occupied.append(bbox)
            placed.append(
                PlacedInstance(
                    asset=asset,
                    bbox=bbox,
                    attempts=attempts,
                    source_path=str(asset.path),
                    sampled={"angle": scaled.angle, "scale": scaled.scale},
                )
            )

        final, final_origin = center_crop(canvas, (out_w, out_h))
        labels = self.serialize_labels(placed, final_origin, out_w, out_h)
        if not labels:
            return None

        final = apply_filter_groups(final, self.data.get("final_filters", {}), rng)

        image_format = self.data["output"]["image_format"].lower()
        suffix = "jpg" if image_format == "jpeg" else image_format
        stem = f"image_{index:06d}"
        image_path = images_dir / f"{stem}.{suffix}"
        label_path = labels_dir / f"{stem}.txt"
        write_image(image_path, final, image_format)
        label_path.write_text("\n".join(labels) + "\n", encoding="utf-8")

        debug_path = None
        if index < self.config.debug_count:
            debug = self.draw_debug(final, labels)
            debug_path = debug_dir / f"{stem}_overlay.jpg"
            write_image(debug_path, debug, "jpg")

        return {
            "index": index,
            "image_path": str(image_path),
            "label_path": str(label_path),
            "debug_path": str(debug_path) if debug_path else None,
            "background_path": str(background_path),
            "perspective": perspective.params,
            "crop_size": crop_size,
            "crop_origin": crop_origin,
            "final_crop_origin": final_origin,
            "instances": [
                {
                    "class_id": item.asset.class_id,
                    "class_name": item.asset.class_name,
                    "bbox": item.bbox,
                    "attempts": item.attempts,
                    "source_path": item.source_path,
                    "sampled": item.sampled,
                }
                for item in placed
            ],
        }

    def sample_crop_size(self, rng: np.random.Generator) -> int:
        low, high = self.data["sampling"]["final_crop_size_range"]
        return int(rng.integers(int(low), int(high) + 1))

    def sample_perspective(self, size: tuple[int, int], rng: np.random.Generator) -> PerspectiveSample:
        settings = self.data["perspective_transformations"]
        enabled = rng.random() <= float(settings.get("probability", 0.0))
        if not enabled:
            return PerspectiveSample(False, {"enabled": False})
        scale = rng.uniform(*settings.get("scale_range", [0.0, 0.02]))
        shear = rng.uniform(*settings.get("shear_range", [-0.015, 0.015]))
        return PerspectiveSample(True, {"enabled": True, "scale": float(scale), "shear": float(shear)})

    def generate_background(
        self,
        path: Path,
        work_size: tuple[int, int],
        perspective: PerspectiveSample,
        rng: np.random.Generator,
    ) -> np.ndarray:
        image = read_rgb(path)
        tiled = tile_background(image, work_size)
        transformed = center_crop(tiled, work_size)[0]
        transformed = apply_filter_groups(transformed, self.data.get("background_filters", {}), rng)
        affine = self.data["background_affine_transformations"]
        angle = sample_optional_range(affine["rotation"]["angle_range"], affine["rotation"]["probability"], rng, default=0.0)
        scale = sample_optional_range(affine["scaling"]["scale_range"], affine["scaling"]["probability"], rng, default=1.0)
        translate_x = sample_optional_range(affine["translation"]["translate_range"], affine["translation"]["probability"], rng, default=0.0)
        translate_y = sample_optional_range(affine["translation"]["translate_range"], affine["translation"]["probability"], rng, default=0.0)
        transformed = apply_rgb_affine(transformed, angle, scale, translate_x, translate_y)
        return apply_perspective(transformed, perspective_matrix_for(transformed.shape[1], transformed.shape[0], perspective))

    def sample_foreground_instances(self, rng: np.random.Generator) -> list[Asset]:
        low, high = self.data["sampling"]["foreground_instances_range"]
        count = int(rng.integers(int(low), int(high) + 1))
        indices = rng.integers(0, len(self.foregrounds), count)
        return [self.foregrounds[int(index)] for index in indices]

    def generate_foreground(self, asset: Asset, perspective: PerspectiveSample, rng: np.random.Generator) -> ForegroundInstance:
        image = read_rgba(asset.path)
        image = apply_filter_groups(image, self.data.get("foreground_filters", {}), rng, preserve_alpha=True)
        rotation = self.data["foreground_affine_transformations"]["rotation"]
        angle = sample_optional_range(rotation["angle_range"], rotation["probability"], rng, default=0.0)
        image = rotate_rgba(image, angle, rotation["mode"])
        image = apply_perspective(image, perspective_matrix_for(image.shape[1], image.shape[0], perspective))
        bbox = visible_bbox(image)
        if bbox is None:
            raise ValueError(f"Foreground became invisible: {asset.path}")
        return ForegroundInstance(image=image, visible_bbox=bbox, asset=asset, angle=angle)

    def scale_foreground(self, instance: ForegroundInstance, output_width: int, rng: np.random.Generator) -> ForegroundInstance:
        min_scale, max_scale = self.data["sampling"]["foreground_scale_range"]
        scale = float(rng.uniform(float(min_scale), float(max_scale)))
        target_width = max(1, int(output_width * scale))
        resized = resize_rgba(instance.image, target_width)
        bbox = visible_bbox(resized)
        if bbox is None:
            raise ValueError(f"Foreground became invisible after scaling: {instance.asset.path}")
        return ForegroundInstance(resized, bbox, instance.asset, instance.angle, scale)

    def place_foreground(
        self,
        canvas: np.ndarray,
        instance: ForegroundInstance,
        occupied: list[BBox],
        rng: np.random.Generator,
    ) -> tuple[int, int, BBox, int] | None:
        h, w = canvas.shape[:2]
        fh, fw = instance.image.shape[:2]
        if fw >= w or fh >= h:
            return None
        max_attempts = int(self.data["sampling"]["max_placement_attempts"])
        min_distance = int(self.data["sampling"]["min_instance_distance_px"])
        lx1, ly1, lx2, ly2 = instance.visible_bbox
        for attempt in range(1, max_attempts + 1):
            x = int(rng.integers(0, w - fw))
            y = int(rng.integers(0, h - fh))
            bbox = (x + lx1, y + ly1, x + lx2, y + ly2)
            expanded = expand_rect(bbox, min_distance)
            if any(rects_intersect(expanded, other) for other in occupied):
                continue
            return x, y, bbox, attempt
        return None

    def serialize_labels(self, placed: list[PlacedInstance], origin: tuple[int, int], width: int, height: int) -> list[str]:
        labels: list[str] = []
        ox, oy = origin
        for item in placed:
            x1, y1, x2, y2 = item.bbox
            clipped = clip_bbox((x1 - ox, y1 - oy, x2 - ox, y2 - oy), width, height)
            if clipped is None:
                continue
            cx = ((clipped[0] + clipped[2]) / 2) / width
            cy = ((clipped[1] + clipped[3]) / 2) / height
            bw = (clipped[2] - clipped[0]) / width
            bh = (clipped[3] - clipped[1]) / height
            labels.append(f"{item.asset.class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        return labels

    def draw_debug(self, image: np.ndarray, labels: list[str]) -> np.ndarray:
        out = image.copy()
        h, w = out.shape[:2]
        for line in labels:
            class_id, cx, cy, bw, bh = line.split()
            x1 = int((float(cx) - float(bw) / 2) * w)
            y1 = int((float(cy) - float(bh) / 2) * h)
            x2 = int((float(cx) + float(bw) / 2) * w)
            y2 = int((float(cy) + float(bh) / 2) * h)
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 80), 3)
            cv2.putText(out, class_id, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 80), 2)
        return out

    def write_data_yaml(self, output_dir: Path) -> None:
        data = {
            "path": str(output_dir),
            "train": "images",
            "names": {index: name for index, name in enumerate(self.class_names)},
        }
        (output_dir / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def sample_optional_range(values: list[float], probability: float, rng: np.random.Generator, default: float) -> float:
    if rng.random() > float(probability):
        return default
    return float(rng.uniform(float(values[0]), float(values[1])))


def perspective_matrix_for(width: int, height: int, sample: PerspectiveSample) -> np.ndarray | None:
    if not sample.enabled:
        return None
    scale = float(sample.params["scale"])
    shear = float(sample.params["shear"])
    inset_x = scale * width
    inset_y = scale * height
    src = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    dst = np.float32(
        [
            [inset_x + shear * width, inset_y],
            [width - inset_x + shear * width, inset_y],
            [width - inset_x - shear * width, height - inset_y],
            [inset_x - shear * width, height - inset_y],
        ]
    )
    return cv2.getPerspectiveTransform(src, dst)
