from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Sequence


DEFAULT_SPATIAL_BINS = 8


def spatial_region(x: float, y: float, width: float, height: float) -> str:
    """Map an output-space point to a stable 3x3 region label."""
    columns = ("left", "center", "right")
    rows = ("top", "middle", "bottom")
    column = min(2, max(0, int((float(x) / max(float(width), 1.0)) * 3)))
    row = min(2, max(0, int((float(y) / max(float(height), 1.0)) * 3)))
    return f"{rows[row]}-{columns[column]}"


def clipped_sides(projected_bbox: Sequence[float], width: int, height: int) -> tuple[str, ...]:
    x1, y1, x2, y2 = projected_bbox
    return tuple(
        side
        for side, clipped in (
            ("left", x1 < 0),
            ("top", y1 < 0),
            ("right", x2 > width),
            ("bottom", y2 > height),
        )
        if clipped
    )


def bounded_spatial_histogram(
    normalized_points: Iterable[tuple[float, float]], *, bins: int = DEFAULT_SPATIAL_BINS
) -> dict[str, Any]:
    """Return a fixed-size row-major histogram for normalized candidate centers."""
    if bins < 1 or bins > 16:
        raise ValueError("spatial histogram bins must be between 1 and 16")
    counts = [0] * (bins * bins)
    for x, y in normalized_points:
        column = min(bins - 1, max(0, int(float(x) * bins)))
        row = min(bins - 1, max(0, int(float(y) * bins)))
        counts[row * bins + column] += 1
    return {"bins": bins, "counts": counts}


def build_rejection_record(
    *,
    slot: int,
    candidate_attempt: int,
    object_attempt: int,
    asset: str,
    class_name: str | None,
    group: str,
    scale: float,
    rotation_degrees: float,
    estimated_size: tuple[float, float],
    requested_objects: int,
    stage: str,
    reason: str,
    placement_attempts: int = 0,
    blocking_counts: dict[str, int] | None = None,
    spatial_histogram: dict[str, Any] | None = None,
    best_failed: dict[str, Any] | None = None,
    projected_bbox: Sequence[float] | None = None,
    clipped_bbox: Sequence[int] | None = None,
    clipped_sides: Sequence[str] = (),
    visibility: float | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": 1,
        "slot": int(slot),
        "candidate_attempt": int(candidate_attempt),
        "object_attempt": int(object_attempt),
        "asset": asset,
        "class_name": class_name or "unknown",
        "group": group,
        "scale": round(float(scale), 8),
        "rotation_degrees": round(float(rotation_degrees), 6),
        "estimated_size": [round(float(value), 3) for value in estimated_size],
        "requested_objects": int(requested_objects),
        "stage": stage,
        "reason": reason,
        "placement_attempts": int(placement_attempts),
        "blocking_counts": dict(sorted((blocking_counts or {}).items())),
        "spatial_histogram": spatial_histogram
        or {"bins": DEFAULT_SPATIAL_BINS, "counts": [0] * (DEFAULT_SPATIAL_BINS**2)},
        "clipped_sides": list(clipped_sides),
        "region": region or "unknown",
    }
    if best_failed is not None:
        record["best_failed"] = best_failed
    if projected_bbox is not None:
        record["projected_bbox"] = [round(float(value), 3) for value in projected_bbox]
    if clipped_bbox is not None:
        record["clipped_bbox"] = [int(value) for value in clipped_bbox]
    if visibility is not None:
        record["visibility"] = round(float(visibility), 8)
    return record


def _scale_band(value: float) -> str:
    low = max(0, int(float(value) * 10)) / 10
    return f"{low:.2f}-{low + 0.1:.2f}"


def _rotation_band(value: float) -> str:
    normalized = abs(float(value)) % 180
    low = int(normalized // 15) * 15
    return f"{low}-{low + 15}"


def _group(
    rejections: list[dict[str, Any]], attempts: list[dict[str, Any]], key
) -> dict[str, dict[str, float | int]]:
    counts = Counter(str(key(record)) for record in rejections)
    totals = Counter(str(key(record)) for record in attempts)
    return {
        name: {
            "rejections": counts.get(name, 0),
            "attempts": totals.get(name, 0),
            "rate": counts.get(name, 0) / totals[name] if totals.get(name, 0) else None,
        }
        for name in sorted(set(counts) | set(totals))
    }


def _event_group(records: list[dict[str, Any]], key, denominator: int) -> dict[str, dict[str, float | int]]:
    counts = Counter(str(key(record)) for record in records)
    return {
        name: {
            "rejections": count,
            "object_attempts": denominator,
            "rate": count / denominator if denominator else 0.0,
        }
        for name, count in sorted(counts.items())
    }


def summarize_placement_diagnostics(
    records: Iterable[dict[str, Any]], accepted: Iterable[dict[str, Any]] = ()
) -> dict[str, Any]:
    materialized = list(records)
    attempts = [*list(accepted), *materialized]
    return {
        "schema_version": 1,
        "total_rejections": len(materialized),
        "accepted_objects": len(attempts) - len(materialized),
        "total_object_attempts": len(attempts),
        "overall_rejection_rate": len(materialized) / len(attempts) if attempts else 0.0,
        "by_asset": _group(materialized, attempts, lambda item: item.get("asset", "unknown")),
        "by_class": _group(materialized, attempts, lambda item: item.get("class_name", "unknown")),
        "by_scale_band": _group(materialized, attempts, lambda item: _scale_band(item.get("scale", 0.0))),
        "by_rotation_band": _group(
            materialized, attempts, lambda item: _rotation_band(item.get("rotation_degrees", 0.0))
        ),
        "by_object_count": _group(materialized, attempts, lambda item: item.get("requested_objects", 0)),
        "by_region": _group(materialized, attempts, lambda item: item.get("region", "unknown")),
        "by_stage": _event_group(materialized, lambda item: item.get("stage", "unknown"), len(attempts)),
        "by_reason": _event_group(materialized, lambda item: item.get("reason", "unknown"), len(attempts)),
    }
