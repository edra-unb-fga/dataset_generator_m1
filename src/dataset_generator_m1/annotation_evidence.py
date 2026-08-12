from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


MASK_FORMAT = "npz-cropped-alpha-v1"


@dataclass(frozen=True)
class EncodedMaskEvidence:
    archive_bytes: bytes
    manifest: dict[str, Any]


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
