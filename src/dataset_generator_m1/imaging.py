from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .types import BBox


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGB"))


def read_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"))


def write_image(path: Path, image: np.ndarray, image_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if image_format.lower() in {"jpg", "jpeg"}:
        Image.fromarray(image.astype(np.uint8), mode="RGB").save(path, quality=95, subsampling=1)
    else:
        Image.fromarray(image.astype(np.uint8), mode="RGB").save(path)


def visible_bbox(rgba: np.ndarray, alpha_threshold: int = 8) -> BBox | None:
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > alpha_threshold)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def crop_bbox(image: np.ndarray, bbox: BBox) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    return image[y1:y2, x1:x2].copy()


def resize_rgba(image: np.ndarray, width: int) -> np.ndarray:
    height = max(1, round(image.shape[0] * width / image.shape[1]))
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def rotate_rgba(image: np.ndarray, angle: float, mode: str) -> np.ndarray:
    h, w = image.shape[:2]
    center = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]
    rotated = cv2.warpAffine(
        image,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    if mode == "circle":
        bbox = visible_bbox(rotated)
        if bbox is not None:
            rotated = crop_bbox(rotated, bbox)
    return rotated


def tile_background(image: np.ndarray, min_size: tuple[int, int]) -> np.ndarray:
    target_w, target_h = min_size
    tile_h, tile_w = image.shape[:2]
    repeats_x = max(3, int(np.ceil(target_w / tile_w)) + 2)
    repeats_y = max(3, int(np.ceil(target_h / tile_h)) + 2)
    return np.tile(image, (repeats_y, repeats_x, 1))


def apply_rgb_affine(
    image: np.ndarray,
    angle: float,
    scale: float,
    translate_x: float,
    translate_y: float,
) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    matrix[0, 2] += translate_x * w
    matrix[1, 2] += translate_y * h
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)


def apply_perspective(image: np.ndarray, matrix: np.ndarray | None) -> np.ndarray:
    if matrix is None:
        return image
    h, w = image.shape[:2]
    channels = image.shape[2] if image.ndim == 3 else 1
    border = (0, 0, 0, 0) if channels == 4 else (0, 0, 0)
    return cv2.warpPerspective(image, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def center_crop(image: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, tuple[int, int]]:
    crop_w, crop_h = size
    h, w = image.shape[:2]
    x = max(0, (w - crop_w) // 2)
    y = max(0, (h - crop_h) // 2)
    return image[y:y + crop_h, x:x + crop_w].copy(), (x, y)


def alpha_composite(base: np.ndarray, foreground: np.ndarray, x: int, y: int) -> None:
    h, w = foreground.shape[:2]
    roi = base[y:y + h, x:x + w]
    alpha = foreground[:, :, 3:4].astype(np.float32) / 255.0
    roi[:] = (foreground[:, :, :3].astype(np.float32) * alpha + roi.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)


def expand_rect(rect: BBox, amount: int) -> BBox:
    x1, y1, x2, y2 = rect
    return x1 - amount, y1 - amount, x2 + amount, y2 + amount


def rects_intersect(a: BBox, b: BBox) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def clip_bbox(bbox: BBox, width: int, height: int) -> BBox | None:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))
    x2 = max(0, min(width, x2))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2

