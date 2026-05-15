"""Example augmentation pipeline leveraging imgaug with configurable settings.

This script illustrates how to:
  * Parse CLI arguments for dataset paths and configuration overrides.
  * Build a light-to-moderate augmentation sequence derived from imgaug's heavy example.
  * Apply augmentations to YOLO-format datasets (images + bounding boxes).
  * Emit augmented samples and labels into a new output directory.

It is meant as a starting point and can be extended with concurrency, richer
logging, and additional error handling as the project evolves.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, cast

# imgaug provides the augmentation primitives; ignore typing complaints if stubs are absent.
import imageio.v3 as iio
import numpy as np

if not hasattr(np, "sctypes"):
    np.sctypes = {  # type: ignore[attr-defined]
        "int": [np.int8, np.int16, np.int32, np.int64],
        "uint": [np.uint8, np.uint16, np.uint32, np.uint64],
        "float": [np.float16, np.float32, np.float64],
        "complex": [np.complex64, np.complex128],
        "others": [np.bool_, np.bytes_, np.str_, np.object_],
        "datetime": [np.datetime64],
        "timedelta": [np.timedelta64],
    }

import imgaug.augmenters as iaa  # type: ignore
import imgaug.parameters as iap  # type: ignore
from imgaug.augmenters import segmentation as iaa_seg  # type: ignore
import yaml
from imgaug.augmentables.bbs import BoundingBox, BoundingBoxesOnImage  # type: ignore
from imgaug.augmentables.polys import Polygon, PolygonsOnImage  # type: ignore



@dataclass
class AugmentConfig:
    """Typed view over the YAML configuration."""

    augment: Dict[str, Any]
    defaults: Dict[str, Any]
    io: Dict[str, Any]
    paths: Dict[str, Any]

    @staticmethod
    def from_file(path: Path) -> "AugmentConfig":
        with path.open("r", encoding="utf-8") as fh:
            loaded_raw: Any = yaml.safe_load(fh)
        if isinstance(loaded_raw, dict):
            raw = cast(Dict[str, Any], loaded_raw)
        else:
            raw = cast(Dict[str, Any], {})

        io_source = raw.get("io")
        if not isinstance(io_source, dict):
            io_source = raw.get("aio", {})
        if not isinstance(io_source, dict):
            io_source = {}

        return AugmentConfig(
            augment=cast(Dict[str, Any], raw.get("augment", {})),
            defaults=cast(Dict[str, Any], raw.get("defaults", {})),
            io=cast(Dict[str, Any], io_source),
            paths=cast(Dict[str, Any], raw.get("paths", {})),
        )


@dataclass
class Annotation:
    class_id: str
    poly_index: Optional[int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ImgAug augmentation pipeline example")
    parser.add_argument("--config", "-c", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--input", "-i", type=Path, required=True, help="Root of YOLO dataset")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Destination directory for augmented data")
    parser.add_argument("--split", choices=["train", "val", "test", "all"], help="Dataset split to augment")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on number of images per split")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--manifest", action="store_true", help="Emit manifest.json summarizing augmentations")
    return parser.parse_args()

def ensure_rgb(image: np.ndarray) -> np.ndarray:
    """Guarantee that the image has exactly three channels."""

    if image.ndim == 2:
        image = np.stack([image] * 3, axis=-1)
    elif image.ndim != 3:
        raise ValueError(f"Unsupported image ndim: {image.ndim}")
    else:
        channels = image.shape[2]
        if channels == 3:
            pass
        elif channels == 1:
            image = np.repeat(image, 3, axis=2)
        elif channels == 2:
            gray = image[..., 0]
            image = np.stack([gray, gray, gray], axis=-1)
        elif channels > 3:
            image = image[..., :3]
        else:
            raise ValueError(f"Unsupported channel count: {channels}")
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    return image


def build_sequence(cfg: AugmentConfig) -> Any:
    aug = cfg.augment
    core = cast(Dict[str, Any], aug.get("core", {}) or {})
    geometric = cast(Dict[str, Any], aug.get("geometric", {}) or {})
    texture = cast(Dict[str, Any], aug.get("texture_noise", {}) or {})
    color = cast(Dict[str, Any], aug.get("color", {}) or {})
    segmentation = cast(Dict[str, Any], aug.get("segmentation", {}) or {})

    def tuple_or(default: Sequence[float] | float | None, fallback: Tuple[float, float]) -> Tuple[float, float]:
        if default is None or (isinstance(default, Sequence) and len(default) == 0):
            return fallback
        if isinstance(default, (int, float)):
            return float(default), float(default)
        return tuple(default)  # type: ignore[return-value]

    def ensure_tuple(val: Sequence[float] | float | None, fallback: Tuple[float, float]) -> Tuple[float, float]:
        if val is None:
            return fallback
        if isinstance(val, (int, float)):
            return float(val), float(val)
        return tuple(val)  # type: ignore[return-value]

    def ensure_int_tuple(val: Sequence[int] | int | None, fallback: Tuple[int, int]) -> Tuple[int, int]:
        if val is None:
            return fallback
        if isinstance(val, int):
            return int(val), int(val)
        return tuple(int(v) for v in val)  # type: ignore[return-value]

    def ensure_numeric_or_range(
        val: Sequence[float] | float | None,
        fallback: float | Tuple[float, float],
    ) -> float | Tuple[float, float]:
        if val is None:
            return fallback
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, (list, tuple)):
            cleaned: List[float] = []
            for item in val:
                try:
                    cleaned.append(float(item))
                except (TypeError, ValueError):
                    return fallback
            if not cleaned:
                return fallback
            if len(cleaned) == 1:
                return cleaned[0]
            return tuple(cleaned[:2])  # type: ignore[return-value]
        return fallback

    def ensure_float_or_param(val: Sequence[float] | float | None, fallback: float) -> float | Any:
        if val is None:
            return fallback
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, (list, tuple)):
            cleaned: List[float] = []
            for item in val:
                try:
                    cleaned.append(float(item))
                except (TypeError, ValueError):
                    continue
            if not cleaned:
                return fallback
            if len(cleaned) == 1:
                return cleaned[0]
            low, high = cleaned[0], cleaned[1]
            if low > high:
                low, high = high, low
            return iap.Uniform(low, high)
        return fallback

    blur_cfg = cast(Dict[str, Any], texture.get("blurs", {}) or {})
    blur_prob = float(blur_cfg.get("prob", 0.0))
    blur_someof = ensure_int_tuple(blur_cfg.get("someof"), (1, 1))
    gaussian_sigma = ensure_tuple(blur_cfg.get("gaussian_sigma"), (0.0, 0.8))
    motion_kernel_cfg = blur_cfg.get("motion_kernel", 3)
    motion_kernel_param: Any
    if isinstance(motion_kernel_cfg, (list, tuple)):
        mk_low, mk_high = ensure_int_tuple(motion_kernel_cfg, (3, 3))
        if mk_low > mk_high:
            mk_low, mk_high = mk_high, mk_low
        kernel_candidates = [k for k in range(max(1, mk_low), mk_high + 1) if k % 2 == 1]
        if not kernel_candidates:
            first_candidate = max(1, mk_low)
            kernel_candidates = [first_candidate + (first_candidate + 1) % 2]
        motion_kernel_param = iap.Choice(kernel_candidates)
    else:
        motion_kernel_param = int(motion_kernel_cfg) if motion_kernel_cfg is not None else 3
        if motion_kernel_param < 1:
            motion_kernel_param = 1
        if motion_kernel_param % 2 == 0:
            motion_kernel_param += 1
    motion_angle = ensure_tuple(blur_cfg.get("motion_angle"), (-12, 12))

    perturb_cfg = cast(Dict[str, Any], texture.get("perturb", {}) or {})
    perturb_prob = float(perturb_cfg.get("prob", 0.0))
    perturb_someof = ensure_int_tuple(perturb_cfg.get("someof"), (1, 1))
    noise_scale = ensure_tuple(perturb_cfg.get("additive_gaussian_noise"), (0.0, 0.015))
    dropout_range = ensure_tuple(perturb_cfg.get("dropout"), (0.0, 0.03))
    dropout_per_channel_param: Any = ensure_float_or_param(perturb_cfg.get("dropout_per_channel"), 0.1)
    brightness_range = ensure_tuple(perturb_cfg.get("brightness_add"), (-4, 4))

    cutout_cfg = cast(Dict[str, Any], perturb_cfg.get("cutout", {}) or {})
    cutout_prob = float(cutout_cfg.get("prob", 0.0))
    cutout_iterations = ensure_int_tuple(cutout_cfg.get("iterations"), (1, 2))
    cutout_size = ensure_tuple(cutout_cfg.get("size"), (0.02, 0.08))
    cutout_squared = bool(cutout_cfg.get("squared", True))
    cutout_fill_mode = str(cutout_cfg.get("fill_mode", "constant"))
    cutout_cval = ensure_numeric_or_range(cutout_cfg.get("cval"), 0.0)
    cutout_per_channel = bool(cutout_cfg.get("per_channel", False))

    voronoi_cfg = cast(Dict[str, Any], segmentation.get("uniform_voronoi", {}) or {})
    voronoi_prob = float(voronoi_cfg.get("prob", 0.0))
    voronoi_n_points = voronoi_cfg.get("n_points", (80, 160))
    voronoi_p_replace = ensure_numeric_or_range(voronoi_cfg.get("p_replace"), 1.0)
    voronoi_max_size = voronoi_cfg.get("max_size", 128)
    voronoi_interp = voronoi_cfg.get("interpolation", "linear")

    seq = iaa.Sequential(
        [
            iaa.Fliplr(core.get("flip_lr", 0.5)),
            iaa.Flipud(core.get("flip_ud", 0.0)),
            iaa.Crop(percent=tuple_or(core.get("crop_percent"), (0.0, 0.02))),
            iaa.LinearContrast(tuple_or(core.get("contrast"), (0.9, 1.1))),
            iaa.Sometimes(
                geometric.get("prob", 0.3),
                iaa.Affine(
                    scale={
                        "x": tuple_or(geometric.get("affine", {}).get("scale"), (0.95, 1.05)),
                        "y": tuple_or(geometric.get("affine", {}).get("scale"), (0.95, 1.05)),
                    },
                    translate_percent={
                        "x": tuple_or(geometric.get("affine", {}).get("translate"), (-0.05, 0.05)),
                        "y": tuple_or(geometric.get("affine", {}).get("translate"), (-0.05, 0.05)),
                    },
                    rotate=tuple_or(geometric.get("affine", {}).get("rotate"), (-8, 8)),
                    shear=tuple_or(geometric.get("affine", {}).get("shear"), (-4, 4)),
                    order=[0, 1],
                    mode="reflect",
                ),
            ),
            iaa.Sometimes(
                geometric.get("prob", 0.3),
                iaa.PerspectiveTransform(scale=tuple_or(geometric.get("perspective_scale"), (0.0, 0.01))),
            ),
            iaa.Sometimes(
                blur_prob,
                iaa.SomeOf(
                    blur_someof,
                    [
                        iaa.GaussianBlur(sigma=gaussian_sigma),
                        iaa.MotionBlur(k=motion_kernel_param, angle=motion_angle),
                    ],
                    random_order=True,
                ),
            ),
            iaa.Sometimes(
                perturb_prob,
                iaa.SomeOf(
                    perturb_someof,
                    [
                        iaa.AdditiveGaussianNoise(scale=tuple(x * 255 for x in noise_scale), per_channel=perturb_cfg.get("per_channel", 0.3)),
                        iaa.Dropout(dropout_range, per_channel=dropout_per_channel_param),
                        iaa.Sometimes(
                            cutout_prob,
                            iaa.Cutout(
                                nb_iterations=cutout_iterations,
                                size=cutout_size,
                                squared=cutout_squared,
                                fill_mode=cutout_fill_mode,
                                cval=cutout_cval,
                                fill_per_channel=cutout_per_channel,
                            ),
                        ),
                        iaa.Add(
                            brightness_range,
                            per_channel=ensure_float_or_param(perturb_cfg.get("brightness_per_channel"), 0.3),
                        ),
                    ],
                    random_order=True,
                ),
            ),
            iaa.Sometimes(
                color.get("prob", 0.4),
                iaa.Sequential(
                    [
                        iaa.Multiply(
                            tuple_or(color.get("multiply"), (0.92, 1.08)),
                            per_channel=ensure_float_or_param(color.get("multiply_per_channel"), 0.2),
                        ),
                        iaa.AddToHueAndSaturation(tuple_or(color.get("hue_shift"), (-6, 6))),
                        iaa.Grayscale(alpha=tuple_or(color.get("desaturate_alpha"), (0.0, 0.15))),
                    ],
                    random_order=False,
                ),
            ),
            iaa.Sometimes(
                voronoi_prob,
                iaa_seg.UniformVoronoi(
                    n_points=voronoi_n_points,
                    p_replace=voronoi_p_replace,
                    max_size=voronoi_max_size,
                    interpolation=voronoi_interp,
                ),
            ),
        ],
        random_order=True,
    )

    return seq


def discover_splits(dataset_root: Path) -> Dict[str, Path]:
    """Return mapping of split name to image directory."""
    candidates = {}
    data_yaml = dataset_root / "data.yaml"
    dataset_yaml = dataset_root / "dataset.yaml"
    if data_yaml.exists():
        with data_yaml.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for split in ("train", "val", "test"):
            rel = data.get(split)
            if not rel:
                continue
            candidate = (dataset_root / rel).resolve()
            if not candidate.exists():
                fallback = (dataset_root / split / "images").resolve()
                if fallback.exists():
                    candidate = fallback
                else:
                    continue
            candidates[split] = candidate
    elif dataset_yaml.exists():
        with dataset_yaml.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for split in ("train", "val", "test"):
            rel = data.get(split)
            if not rel:
                continue
            candidate = (dataset_root / rel).resolve()
            if not candidate.exists():
                fallback = (dataset_root / split / "images").resolve()
                if fallback.exists():
                    candidate = fallback
                else:
                    continue
            candidates[split] = candidate
    else:
        for split in ("train", "val", "test"):
            split_dir = dataset_root / split / "images"
            if split_dir.exists():
                candidates[split] = split_dir.resolve()
    if not candidates:
        root_images = (dataset_root / "images").resolve()
        root_labels = dataset_root / "labels"
        if root_images.exists() and root_labels.exists():
            candidates["train"] = root_images
    return candidates


def iter_samples(image_dir: Path, cfg: AugmentConfig) -> Iterator[Tuple[Path, Path]]:
    suffixes = tuple(cfg.paths.get("image_suffixes", [".jpg", ".jpeg", ".png"]))
    label_suffix = cfg.paths.get("label_suffix", ".txt")
    for image_path in sorted(image_dir.glob("*")):
        if image_path.suffix.lower() not in suffixes:
            continue
        label_path = image_dir.parent / "labels" / image_path.name.replace(image_path.suffix, label_suffix)
        if not label_path.exists():
            continue
        yield image_path, label_path


def parse_yolo_annotations(
    label_path: Path,
    width: int,
    height: int,
) -> Tuple[List[Annotation], BoundingBoxesOnImage, PolygonsOnImage]:
    annotations: List[Annotation] = []
    boxes: List[BoundingBox] = []
    polygons: List[Polygon] = []

    if not label_path.exists():
        return annotations, BoundingBoxesOnImage([], shape=(height, width, 3)), PolygonsOnImage([], shape=(height, width, 3))

    with label_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            parts = raw_line.strip().split()
            if len(parts) < 5:
                continue
            class_id = parts[0]
            try:
                values = list(map(float, parts[1:]))
            except ValueError:
                continue

            poly_index: Optional[int] = None
            if len(values) == 4:
                cx, cy, w, h = values
                x_center = cx * width
                y_center = cy * height
                bw = w * width
                bh = h * height
                x1 = x_center - bw / 2
                y1 = y_center - bh / 2
                x2 = x_center + bw / 2
                y2 = y_center + bh / 2
            elif len(values) >= 6 and len(values) % 2 == 0:
                xs = values[0::2]
                ys = values[1::2]
                points = [(x * width, y * height) for x, y in zip(xs, ys)]
                if len(points) < 3:
                    continue
                x1 = min(xs) * width
                y1 = min(ys) * height
                x2 = max(xs) * width
                y2 = max(ys) * height
                polygon = Polygon(points, label=class_id)
                poly_index = len(polygons)
                polygons.append(polygon)
            else:
                continue

            bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, label=class_id)
            boxes.append(bbox)
            annotations.append(Annotation(class_id=class_id, poly_index=poly_index))

    return (
        annotations,
        BoundingBoxesOnImage(boxes, shape=(height, width, 3)),
        PolygonsOnImage(polygons, shape=(height, width, 3)),
    )


def serialize_annotations(
    annotations: List[Annotation],
    augmented_bbs: BoundingBoxesOnImage,
    original_bbs: BoundingBoxesOnImage,
    augmented_polys: Optional[PolygonsOnImage],
    width: int,
    height: int,
    min_iou: float,
    allow_empty: bool,
) -> List[str]:
    lines: List[str] = []
    image_shape = (height, width, 3)
    polygons_list = augmented_polys.polygons if augmented_polys is not None else []

    for idx, annotation in enumerate(annotations):
        aug_bb = augmented_bbs.bounding_boxes[idx]
        orig_bb = original_bbs.bounding_boxes[idx]

        clipped_bb = aug_bb.clip_out_of_image(image_shape)
        box_area = max((clipped_bb.x2 - clipped_bb.x1), 0) * max((clipped_bb.y2 - clipped_bb.y1), 0)
        if box_area <= 0:
            continue

        original_area = max((orig_bb.x2 - orig_bb.x1), 0) * max((orig_bb.y2 - orig_bb.y1), 0)
        if original_area <= 0:
            continue

        overlap_ratio = box_area / original_area if original_area else 0.0
        if overlap_ratio < min_iou:
            continue

        if annotation.poly_index is not None and augmented_polys is not None:
            poly = polygons_list[annotation.poly_index]
            clipped_poly = poly.clip_out_of_image(image_shape)
            if isinstance(clipped_poly, list):
                candidates = [p for p in clipped_poly if p is not None]
            elif clipped_poly is not None:
                candidates = [clipped_poly]
            else:
                candidates = []
            if not candidates:
                continue
            best_poly = max(candidates, key=lambda p: p.area)
            shapely_poly = best_poly.to_shapely_polygon()
            coords = list(shapely_poly.exterior.coords)
            if len(coords) < 4:
                continue
            coord_tokens = []
            for x_val, y_val in coords[:-1]:
                nx = np.clip(x_val / width, 0.0, 1.0)
                ny = np.clip(y_val / height, 0.0, 1.0)
                coord_tokens.append(f"{nx:.6f} {ny:.6f}")
            lines.append(f"{annotation.class_id} {' '.join(coord_tokens)}")
        else:
            cx = ((clipped_bb.x1 + clipped_bb.x2) / 2) / width
            cy = ((clipped_bb.y1 + clipped_bb.y2) / 2) / height
            bw = (clipped_bb.x2 - clipped_bb.x1) / width
            bh = (clipped_bb.y2 - clipped_bb.y1) / height
            lines.append(f"{annotation.class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

    if not lines and not allow_empty:
        raise ValueError("All annotations were dropped after augmentation")

    return lines


def chunked(iterable: Iterable, limit: Optional[int]) -> Iterable:
    if limit is None:
        return iterable
    return islice(iterable, limit)


def ensure_out_dirs(base: Path, split: str) -> Tuple[Path, Path]:
    image_dir = base / split / "images"
    label_dir = base / split / "labels"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    return image_dir, label_dir


def augment_dataset(args: argparse.Namespace, cfg: AugmentConfig) -> Dict:
    np.random.seed(args.seed or cfg.defaults.get("seed", 42))
    seq = build_sequence(cfg)
    splits = discover_splits(args.input)
    chosen_split = args.split or cfg.defaults.get("split", "all")
    if chosen_split == "all":
        target_splits = list(splits.keys())
    else:
        target_splits = [chosen_split]

    stats = {"processed": 0, "written": 0, "skipped": []}
    min_iou = float(cfg.io.get("min_bbox_iou", 0.05))
    allow_empty = bool(cfg.io.get("allow_empty", False))
    aug_per_image = int(cfg.io.get("augmentations_per_image", 1))
    keep_original = bool(cfg.io.get("keep_original", False))
    debug_preview_budget = int(cfg.io.get("debug_preview", 0) or 0)
    debug_previews_written = 0
    debug_dirs: Dict[str, Path] = {}
    limit = args.limit if args.limit is not None else cfg.defaults.get("limit")

    for split in target_splits:
        if split not in splits:
            continue
        image_dir = splits[split]
        out_images, out_labels = ensure_out_dirs(args.output, split)
        for image_path, label_path in chunked(iter_samples(image_dir, cfg), limit):
            stats["processed"] += 1
            image = iio.imread(image_path)
            image = ensure_rgb(image)
            if image.shape[-1] != 3:
                raise ValueError(f"Expected 3-channel image after normalization, got shape {image.shape} for {image_path}")
            height, width = image.shape[:2]
            annotations, bbs, polys = parse_yolo_annotations(label_path, width, height)
            if not annotations:
                stats["skipped"].append({
                    "image": str(image_path),
                    "reason": "No valid annotations found",
                })
                continue

            if keep_original:
                stem = image_path.stem
                original_image_path = out_images / f"{stem}{image_path.suffix}"
                original_label_path = out_labels / f"{stem}{cfg.paths.get('label_suffix', '.txt')}"
                iio.imwrite(original_image_path, image)
                original_label_path.write_text(label_path.read_text(encoding="utf-8"), encoding="utf-8")
                stats["written"] += 1

            for idx in range(aug_per_image):
                deterministic_seq = seq.to_deterministic()
                augmented_image = deterministic_seq(image=image)
                augmented_bbs = deterministic_seq(bounding_boxes=bbs)
                augmented_polys = (
                    deterministic_seq(polygons=polys) if polys.polygons else None
                )
                try:
                    yolo_lines = serialize_annotations(
                        annotations,
                        augmented_bbs,
                        bbs,
                        augmented_polys,
                        width=augmented_image.shape[1],
                        height=augmented_image.shape[0],
                        min_iou=min_iou,
                        allow_empty=allow_empty,
                    )
                except ValueError as exc:
                    stats["skipped"].append({
                        "image": str(image_path),
                        "reason": str(exc),
                    })
                    continue

                stem = image_path.stem
                aug_name = f"{stem}_aug{idx:02d}"
                out_image_path = out_images / f"{aug_name}{image_path.suffix}"
                out_label_path = out_labels / f"{aug_name}{cfg.paths.get('label_suffix', '.txt')}"

                iio.imwrite(out_image_path, augmented_image)
                with out_label_path.open("w", encoding="utf-8") as fh:
                    fh.write("\n".join(yolo_lines))
                stats["written"] += 1

                if debug_preview_budget > 0 and debug_previews_written < debug_preview_budget:
                    debug_dir = debug_dirs.get(split)
                    if debug_dir is None:
                        debug_dir = args.output / split / "debug"
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        debug_dirs[split] = debug_dir

                    debug_frame = augmented_image.copy()
                    if augmented_polys is not None and augmented_polys.polygons:
                        debug_frame = augmented_polys.draw_on_image(
                            debug_frame,
                            color=(0, 255, 0),
                            alpha=0.6,
                            size=2,
                        )
                    if augmented_bbs.bounding_boxes:
                        debug_frame = augmented_bbs.draw_on_image(
                            debug_frame,
                            color=(255, 0, 0),
                            size=2,
                        )

                    preview_name = f"{aug_name}_debug{debug_previews_written:03d}.png"
                    preview_path = debug_dir / preview_name
                    iio.imwrite(preview_path, debug_frame)
                    debug_previews_written += 1

    return stats


def main() -> None:
    args = parse_args()
    cfg = AugmentConfig.from_file(args.config)

    if args.split:
        cfg.defaults["split"] = args.split
    if args.limit is not None:
        cfg.defaults["limit"] = args.limit

    stats = augment_dataset(args, cfg)

    if args.manifest or cfg.io.get("manifest", True):
        manifest_path = args.output / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
