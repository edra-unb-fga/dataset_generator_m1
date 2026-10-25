from __future__ import annotations

import hashlib
import json
import os
import platform
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ResolvedProfile


DEFAULT_OBSERVATION_PATH = Path(".cache/performance-observations.jsonl")


def _valid_observation(record: dict[str, Any]) -> bool:
    def number(key: str, *, positive: bool = False, integer: bool = False) -> bool:
        value = record.get(key)
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0)
            and (not integer or isinstance(value, int))
        )
    if not number("workers", positive=True, integer=True):
        return False
    if record.get("kind") == "probe":
        return number("duration_seconds", positive=True) and isinstance(record.get("accepted"), bool)
    if record.get("kind") != "production":
        return False
    return (
        number("active_seconds", positive=True) and number("candidate_attempts", positive=True, integer=True)
        and number("accepted_samples", integer=True)
        and record["accepted_samples"] <= record["candidate_attempts"]
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def environment_class() -> dict[str, Any]:
    return {"system": platform.system(), "machine": platform.machine(), "logical_cpu_count": os.cpu_count()}


def performance_fingerprint(resolved: ResolvedProfile) -> str:
    """Cost identity: portable content, relevant software/policy, never count or seed."""
    from .assets import build_asset_catalog
    from .identities import generation_contract, software_identity
    value = generation_contract(resolved, build_asset_catalog(resolved))
    value["profile"].pop("run", None)
    value["candidate_attempt_budget"] = resolved.profile.run.max_candidate_attempts
    policy = resolved.profile.execution.model_dump(mode="json")
    # Worker-count matching/extrapolation is explicit in observation selection.
    for key in ("workers", "cpu_budget", "ram_budget_mb"):
        policy.pop(key, None)
    value["execution_cost_policy"] = policy
    from .performance_version import IMPLEMENTATION
    value["performance_implementation"] = IMPLEMENTATION
    value["software"] = software_identity()
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
        if not isinstance(record, dict):
            warnings.append({"code": "IGNORED_MALFORMED_OBSERVATION", "severity": "info", "line": line_number})
            continue
        if record.get("schema_version") != 2 or not record.get("performance_fingerprint"):
            warnings.append({"code": "IGNORED_STALE_OBSERVATION", "severity": "info", "line": line_number})
            continue
        if not _valid_observation(record):
            warnings.append({"code": "IGNORED_MALFORMED_OBSERVATION", "severity": "info", "line": line_number})
            continue
        # Derive rates from validated counters; cached derived values may be stale
        # or malformed even when the underlying measurements remain usable.
        if record["kind"] == "production":
            record["seconds_per_candidate"] = record["active_seconds"] * record["workers"] / record["candidate_attempts"]
            record["seconds_per_accepted_output"] = record["active_seconds"] / record["accepted_samples"] if record["accepted_samples"] else None
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
        "seconds_per_accepted_output": active_seconds / accepted if accepted else None,
        "stage_work": summary.get("session_stage_timings", summary.get("stage_timings", {})),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return record
