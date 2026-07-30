from __future__ import annotations

import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ResolvedProfile


DEFAULT_OBSERVATION_PATH = Path(".cache/performance-observations.jsonl")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def environment_class() -> dict[str, Any]:
    return {"system": platform.system(), "machine": platform.machine(), "logical_cpu_count": os.cpu_count()}


def performance_fingerprint(resolved: ResolvedProfile) -> str:
    """Identify work cost without coupling estimates to count, seed, or private paths."""
    profile = resolved.profile
    referenced_paths: set[str] = set()

    def collect_paths(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("path"), str):
                referenced_paths.add(value["path"])
            for nested in value.values():
                collect_paths(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_paths(nested)

    collect_paths(resolved.reference_graph)
    relevant_source_hashes = sorted(
        digest for path, digest in resolved.source_hashes.items() if path in referenced_paths
    )
    value = {
        "schema_version": 1,
        "family": profile.family,
        "dimensions": list(profile.output.image_size),
        "assets": profile.assets.model_dump(mode="json"),
        "sampling": profile.sampling.model_dump(mode="json"),
        "scene": profile.scene.model_dump(mode="json"),
        "recipe_selection": profile.background_synthesis.model_dump(mode="json"),
        "recipe_catalog": resolved.recipes.model_dump(mode="json"),
        "appearance": profile.appearance.model_dump(mode="json"),
        "encoding": {
            "format": profile.output.image_format,
            "jpeg_quality": profile.output.jpeg_quality,
        },
        "source_hashes": relevant_source_hashes,
    }
    return _hash(value)


def read_matching_observations(
    path: Path,
    resolved: ResolvedProfile,
    workers: int,
    environment: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.exists():
        return [], []
    environment = environment or environment_class()
    fingerprint = performance_fingerprint(resolved)
    exact_records: list[dict[str, Any]] = []
    cross_worker_records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            warnings.append({"code": "IGNORED_MALFORMED_OBSERVATION", "severity": "info", "line": line_number})
            continue
        if record.get("schema_version") != 2 or not record.get("performance_fingerprint"):
            warnings.append({"code": "IGNORED_STALE_OBSERVATION", "severity": "info", "line": line_number})
            continue
        if record["performance_fingerprint"] == fingerprint and record.get("environment_class") == environment:
            if record.get("workers") == workers:
                exact_records.append(record)
            else:
                cross_worker_records.append(record)
    if exact_records:
        return exact_records, warnings
    if cross_worker_records:
        warnings.append(
            {
                "code": "LOCAL_OBSERVATION_CROSS_WORKER",
                "severity": "info",
                "observed_workers": sorted({item.get("workers") for item in cross_worker_records}),
                "requested_workers": workers,
            }
        )
    return cross_worker_records, warnings


def append_production_observation(
    path: Path,
    resolved: ResolvedProfile,
    *,
    workers: int,
    summary: dict[str, Any],
    environment: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if summary.get("status") not in {"complete", "interrupted"}:
        return None
    active_seconds = float(summary.get("elapsed_seconds", 0.0))
    attempts = int(summary.get("session_candidate_attempts", summary.get("candidate_attempts", 0)))
    accepted = int(summary.get("session_accepted_samples", summary.get("accepted_samples", 0)))
    if active_seconds <= 0 or attempts <= 0:
        return None
    record = {
        "schema_version": 2,
        "kind": "production",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "performance_fingerprint": performance_fingerprint(resolved),
        "family": resolved.profile.family,
        "dimensions": list(resolved.profile.output.image_size),
        "workers": workers,
        "environment_class": environment or environment_class(),
        "active_seconds": active_seconds,
        "paused_seconds": float(summary.get("paused_seconds", 0.0)),
        "candidate_attempts": attempts,
        "accepted_samples": accepted,
        "throughput_images_per_second": accepted / active_seconds,
        "seconds_per_candidate": active_seconds * workers / attempts,
        "stage_work": summary.get("session_stage_timings", summary.get("stage_timings", {})),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return record
