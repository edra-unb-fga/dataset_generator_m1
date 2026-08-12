from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import cv2


MASK_FORMAT = "npz-cropped-alpha-v1"


@dataclass(frozen=True)
class EncodedMaskEvidence:
    archive_bytes: bytes
    manifest: dict[str, Any]


@dataclass(frozen=True)
class PolygonProjection:
    """A measured one-polygon projection of canonical raster mask evidence."""

    polygon: tuple[tuple[int, int], ...]
    reconstruction: np.ndarray
    iou: float
    area_error: float
    components: int
    holes: int
    status: str
    warnings: tuple[dict[str, str], ...]


def visible_coverages(full_coverages: Iterable[np.ndarray]) -> tuple[np.ndarray, ...]:
    """Return each instance's final visible alpha contribution in composition order."""
    full = tuple(_coverage(value) for value in full_coverages)
    if not full:
        return ()
    shape = full[0].shape
    if any(value.shape != shape for value in full):
        raise ValueError("Full coverage arrays must have one shared shape")
    visible: list[np.ndarray] = []
    for index, coverage in enumerate(full):
        contribution = coverage.astype(np.float32) / 255.0
        for later in full[index + 1 :]:
            contribution *= 1.0 - later.astype(np.float32) / 255.0
        visible.append(np.rint(np.clip(contribution, 0.0, 1.0) * 255.0).astype(np.uint8))
    return tuple(visible)


def _mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    union = int(np.logical_or(left, right).sum())
    return 1.0 if union == 0 else float(np.logical_and(left, right).sum() / union)


def _merged_outer_contour(binary: np.ndarray) -> tuple[np.ndarray, int, int]:
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return np.empty((0, 2), dtype=np.int32), 0, 0
    parents = hierarchy[0] if hierarchy is not None else None
    outer = [
        contour[:, 0, :]
        for index, contour in enumerate(contours)
        if parents is None or int(parents[index][3]) < 0
    ]
    holes = 0 if parents is None else sum(1 for item in parents if int(item[3]) >= 0)
    outer.sort(
        key=lambda points: (
            -abs(float(cv2.contourArea(points))),
            int(points[:, 1].min()),
            int(points[:, 0].min()),
        )
    )
    merged = np.asarray(outer[0], dtype=np.int32)
    for segment in outer[1:]:
        distances = ((merged[:, None, :].astype(np.int64) - segment[None, :, :].astype(np.int64)) ** 2).sum(axis=2)
        left, right = np.unravel_index(int(np.argmin(distances)), distances.shape)
        loop = np.concatenate((segment[right:], segment[: right + 1], merged[left : left + 1]))
        merged = np.concatenate((merged[: left + 1], loop, merged[left + 1 :]))
    return merged, len(outer), holes


def polygonize_coverage(
    coverage: np.ndarray,
    *,
    alpha_threshold: int,
    target_iou: float = 0.995,
    target_area_error: float = 0.01,
) -> PolygonProjection:
    """Project exact coverage to one YOLO-compatible polygon with measured loss.

    Holes and disconnected components cannot be represented faithfully by one YOLO
    polygon. They are deterministically filled/bridged and reported instead of
    discarding the exact pool evidence or failing an otherwise useful export.
    """
    value = _coverage(coverage)
    binary_canvas = (value > alpha_threshold).astype(np.uint8)
    ys, xs = np.where(binary_canvas)
    if not len(xs):
        raise ValueError("A segmentation instance cannot be empty")
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    binary = np.ascontiguousarray(binary_canvas[y1:y2, x1:x2])
    contour, components, holes = _merged_outer_contour(binary)
    if len(contour) < 3:
        raise ValueError("A segmentation instance must contain at least three contour points")
    source_area = max(1, int(binary.sum()))
    perimeter = float(cv2.arcLength(contour.reshape((-1, 1, 2)), True))
    epsilons = np.linspace(0.0, max(2.0, perimeter * 0.04), 48)
    candidates: list[tuple[int, float, float, np.ndarray, np.ndarray]] = []
    fallback: tuple[float, float, np.ndarray, np.ndarray] | None = None
    for epsilon in epsilons:
        candidate = cv2.approxPolyDP(contour.reshape((-1, 1, 2)), float(epsilon), True)[:, 0, :]
        if len(candidate) < 3:
            continue
        reconstructed = np.zeros_like(binary)
        cv2.fillPoly(reconstructed, [candidate.astype(np.int32)], 1)
        iou = _mask_iou(binary, reconstructed)
        area_error = abs(int(reconstructed.sum()) - source_area) / source_area
        if fallback is None or (iou, -area_error, -len(candidate)) > (fallback[0], -fallback[1], -len(fallback[2])):
            fallback = (iou, area_error, candidate, reconstructed)
        if iou >= target_iou and area_error <= target_area_error:
            candidates.append((len(candidate), -iou, area_error, candidate, reconstructed))
    if candidates:
        _points, negative_iou, area_error, polygon, reconstruction = min(candidates, key=lambda item: item[:3])
        iou = -negative_iou
    else:
        assert fallback is not None
        iou, area_error, polygon, reconstruction = fallback
    warnings: list[dict[str, str]] = []
    if components > 1:
        warnings.append({"code": "MULTIPLE_COMPONENTS", "message": f"One YOLO polygon bridges {components} disconnected components."})
    if holes:
        warnings.append({"code": "MASK_HOLES_FILLED", "message": f"One YOLO polygon fills {holes} mask hole(s)."})
    if iou < target_iou or area_error > target_area_error:
        warnings.append(
            {
                "code": "POLYGON_FIDELITY_BELOW_TARGET",
                "message": f"Rasterized IoU {iou:.6f}; absolute area error {area_error:.3%}.",
            }
        )
    expanded = np.zeros_like(binary_canvas)
    expanded[y1:y2, x1:x2] = reconstruction
    points = tuple((int(point[0]) + x1, int(point[1]) + y1) for point in polygon)
    return PolygonProjection(
        polygon=points,
        reconstruction=expanded,
        iou=float(iou),
        area_error=float(area_error),
        components=components,
        holes=holes,
        status="complete_with_warnings" if warnings else "complete",
        warnings=tuple(warnings),
    )


def _coverage(value: np.ndarray) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 2 or array.dtype != np.uint8:
        raise ValueError("Coverage arrays must be two-dimensional uint8 values")
    return np.ascontiguousarray(array)


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _crop(array: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    ys, xs = np.where(array > 0)
    if not len(xs):
        raise ValueError("Accepted instance coverage cannot be empty")
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    return np.ascontiguousarray(array[y1:y2, x1:x2]), (x1, y1)


def _array_ref(key: str, array: np.ndarray, origin: tuple[int, int]) -> dict[str, Any]:
    return {
        "key": key,
        "origin": [origin[0], origin[1]],
        "shape": [int(array.shape[0]), int(array.shape[1])],
        "sha256": _digest(array),
        "same_as": None,
    }


def _deterministic_npz(arrays: dict[str, np.ndarray]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for key, array in sorted(arrays.items()):
            payload = io.BytesIO()
            np.save(payload, array, allow_pickle=False)
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return target.getvalue()


def encode_mask_evidence(
    full_coverages: Iterable[np.ndarray],
    visible: Iterable[np.ndarray],
    instance_ids: Iterable[str],
    *,
    image_size: tuple[int, int],
    alpha_threshold: int,
) -> EncodedMaskEvidence:
    full_values = tuple(_coverage(value) for value in full_coverages)
    visible_values = tuple(_coverage(value) for value in visible)
    ids = tuple(str(value) for value in instance_ids)
    if not (len(full_values) == len(visible_values) == len(ids)) or len(set(ids)) != len(ids):
        raise ValueError("Coverage arrays and unique instance IDs must have matching lengths")
    width, height = image_size
    expected_shape = (height, width)
    if not 0 <= alpha_threshold <= 254:
        raise ValueError("alpha_threshold must be between 0 and 254")
    arrays: dict[str, np.ndarray] = {}
    instances: list[dict[str, Any]] = []
    for index, (instance_id, full, final_visible) in enumerate(zip(ids, full_values, visible_values)):
        if full.shape != expected_shape or final_visible.shape != expected_shape:
            raise ValueError(f"Coverage shape must be {expected_shape}")
        full_crop, full_origin = _crop(full)
        full_key = f"i{index:03d}_full"
        arrays[full_key] = full_crop
        full_ref = _array_ref(full_key, full_crop, full_origin)
        if np.array_equal(full, final_visible):
            visible_ref: dict[str, Any] = {"same_as": "full"}
        else:
            visible_crop, visible_origin = _crop(final_visible)
            visible_key = f"i{index:03d}_visible"
            arrays[visible_key] = visible_crop
            visible_ref = _array_ref(visible_key, visible_crop, visible_origin)
        instances.append({"instance_id": instance_id, "full": full_ref, "visible": visible_ref})
    archive_bytes = _deterministic_npz(arrays)
    manifest = {
        "schema_version": 1,
        "format": MASK_FORMAT,
        "image_size": [width, height],
        "alpha_threshold": alpha_threshold,
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "byte_count": len(archive_bytes),
        "instances": instances,
    }
    return EncodedMaskEvidence(archive_bytes=archive_bytes, manifest=manifest)


def _expected_refs(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    for item in manifest.get("instances", []):
        instance_id = str(item.get("instance_id", ""))
        if not instance_id or instance_id in ids:
            raise ValueError("Mask manifest contains invalid or duplicate instance IDs")
        ids.add(instance_id)
        for semantic in ("full", "visible"):
            ref = item.get(semantic, {})
            if ref.get("same_as") == "full" and semantic == "visible":
                continue
            key = ref.get("key")
            if not isinstance(key, str) or not key or key in refs:
                raise ValueError("Mask manifest contains invalid or duplicate array keys")
            refs[key] = ref
    return refs


def decode_mask_evidence(archive_bytes: bytes, manifest: dict[str, Any]) -> dict[str, dict[str, np.ndarray]]:
    if manifest.get("format") != MASK_FORMAT:
        raise ValueError(f"Unsupported mask evidence format: {manifest.get('format')}")
    if hashlib.sha256(archive_bytes).hexdigest() != manifest.get("sha256"):
        raise ValueError("Mask archive hash does not match its manifest")
    if len(archive_bytes) != int(manifest.get("byte_count", -1)):
        raise ValueError("Mask archive byte count does not match its manifest")
    width, height = (int(value) for value in manifest.get("image_size", ()))
    refs = _expected_refs(manifest)
    expected_names = {f"{key}.npy" for key in refs}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or set(names) != expected_names:
                raise ValueError("Mask archive entries do not match the manifest")
            for info in infos:
                key = info.filename.removesuffix(".npy")
                shape = refs[key].get("shape", ())
                expected_bytes = int(np.prod(shape, dtype=np.int64))
                if info.file_size > expected_bytes + 1024:
                    raise ValueError("Mask archive entry exceeds its declared uint8 shape")
        with np.load(io.BytesIO(archive_bytes), allow_pickle=False) as archive:
            arrays = {key: np.asarray(archive[key]) for key in refs}
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Mask archive cannot be decoded without pickle/object data: {exc}") from exc
    expanded: dict[str, np.ndarray] = {}
    for key, ref in refs.items():
        array = arrays[key]
        if array.dtype != np.uint8 or array.ndim != 2:
            raise ValueError("Mask archive arrays must use two-dimensional uint8 dtype, never object/pickle data")
        shape = tuple(int(value) for value in ref.get("shape", ()))
        origin = tuple(int(value) for value in ref.get("origin", ()))
        if array.shape != shape or len(origin) != 2 or _digest(array) != ref.get("sha256"):
            raise ValueError("Mask archive array shape, origin, or hash does not match its manifest")
        x, y = origin
        if x < 0 or y < 0 or x + shape[1] > width or y + shape[0] > height:
            raise ValueError("Mask archive crop lies outside the declared image size")
        canvas = np.zeros((height, width), dtype=np.uint8)
        canvas[y : y + shape[0], x : x + shape[1]] = array
        expanded[key] = canvas
    result: dict[str, dict[str, np.ndarray]] = {}
    for item in manifest["instances"]:
        full = expanded[item["full"]["key"]]
        visible_ref = item["visible"]
        final_visible = full if visible_ref.get("same_as") == "full" else expanded[visible_ref["key"]]
        result[item["instance_id"]] = {"full": full, "visible": final_visible}
    return result
