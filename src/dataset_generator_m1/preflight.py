from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

from .models import ResolvedProfile
from .performance import (
    DEFAULT_OBSERVATION_PATH,
    environment_class,
    performance_fingerprint,
    read_matching_observations,
)


KNOWLEDGE_PATH = Path(__file__).with_name("knowledge") / "performance.json"
@dataclass(frozen=True)
class PreflightRequest:
    resolved: ResolvedProfile
    output_dir: Path
    workers: int
    observation_path: Path = DEFAULT_OBSERVATION_PATH


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _appearance_metadata(resolved: ResolvedProfile) -> dict[str, Any]:
    candidates = [item for item in resolved.profile_metadata if str(item.get("subject", "")).startswith("appearance")]
    if candidates:
        primary = next((item for item in reversed(candidates) if item.get("subject") == "appearance"), candidates[-1])
        risks = [item.get("performance_risk", "none") for item in candidates]
        risk = "confirmation" if "confirmation" in risks else "informational" if "informational" in risks else "none"
        result = {
            **dict(primary),
            "profile_ids": [item.get("id") for item in candidates],
            "performance_risk": risk,
            "warning_codes": list(
                dict.fromkeys(code for item in candidates for code in item.get("warning_codes", ()))
            ),
            "evidence": list(dict.fromkeys(path for item in candidates for path in item.get("evidence", ()))),
        }
        inline = resolved.reference_graph.get("appearance", {}).get("inline", {})
        inline_effects = [item for stage in ("background", "foreground", "final") for item in inline.get(stage, ())]
        if inline_effects:
            result["warning_codes"] = list(dict.fromkeys([*result["warning_codes"], "INLINE_APPEARANCE_UNREVIEWED"]))
            if any(item.get("type") == "RandomFog" for item in inline_effects):
                result["id"] = "local:appearance/inline-random-fog"
                result["performance_risk"] = "confirmation"
                result["warning_codes"] = list(dict.fromkeys([*result["warning_codes"], "RANDOM_FOG_HIGH_COST"]))
                result["evidence"] = list(
                    dict.fromkeys([*result["evidence"], "docs/experiments/native-fog-v1/conclusion.json"])
                )
        return result
    return {
        "id": "local:appearance/undocumented",
        "subject": "appearance",
        "performance_risk": "confirmation",
        "warning_codes": ["UNDOCUMENTED_LOCAL_PROFILE"],
        "evidence": [],
    }


def _append_observations(
    path: Path,
    request: PreflightRequest,
    environment: dict[str, Any],
    observations: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = request.resolved.profile.output.image_size
    with path.open("a", encoding="utf-8") as handle:
        for observation in observations:
            record = {
                "schema_version": 2,
                "kind": "probe",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "contract_hash": request.resolved.contract_hash,
                "performance_fingerprint": performance_fingerprint(request.resolved),
                "family": request.resolved.profile.family,
                "workers": request.workers,
                "dimensions": [width, height],
                "megapixels": width * height / 1_000_000.0,
                "environment_class": environment,
                **observation,
            }
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def estimate_disk(output_dir: Path, resolved: ResolvedProfile) -> dict[str, int | bool]:
    probe = output_dir.resolve()
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    width, height = resolved.profile.output.image_size
    raw_bytes = width * height * 3 * resolved.profile.run.num_images
    encoding_factor = 1.1 if resolved.profile.output.image_format == "png" else 0.6
    estimated_image_bytes = int(raw_bytes * encoding_factor)
    # Coverage archives are sparse and cropped, but preflight intentionally budgets
    # conservatively from the maximum configured instance count. Current reviewed
    # fixtures are substantially smaller than this 0.25 byte/pixel/instance ceiling.
    max_instances = resolved.profile.sampling.instances_per_image[1]
    estimated_mask_bytes = int(width * height * max_instances * 0.25 * resolved.profile.run.num_images)
    estimated_metadata_bytes = resolved.profile.run.num_images * 64 * 1024
    estimated_bytes = estimated_image_bytes + estimated_mask_bytes + estimated_metadata_bytes
    reserve_bytes = 64 * 1024 * 1024
    free_bytes = int(shutil.disk_usage(probe).free)
    return {
        "estimated_output_bytes": estimated_bytes,
        "estimated_image_bytes": estimated_image_bytes,
        "estimated_mask_bytes": estimated_mask_bytes,
        "estimated_metadata_bytes": estimated_metadata_bytes,
        "free_bytes": free_bytes,
        "reserve_bytes": reserve_bytes,
        "sufficient": free_bytes >= estimated_bytes + reserve_bytes,
    }


def _runtime_estimate(
    request: PreflightRequest,
    metadata: dict[str, Any],
    observations: list[dict[str, Any]],
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    profile_id = str(metadata.get("id", "local:appearance/undocumented"))
    entry = knowledge["profiles"].get(profile_id)
    width, height = request.resolved.profile.output.image_size
    megapixels = width * height / 1_000_000.0
    production = [item for item in observations if item.get("kind") == "production"]
    probes = [item for item in observations if item.get("kind") == "probe"]
    if production:
        values = [float(item["seconds_per_candidate"]) for item in production]
        per_candidate = median(values)
        cross_worker = any(item.get("workers") != request.workers for item in production)
        confidence = (
            "local-production-cross-worker"
            if cross_worker
            else "local-production" if len(production) >= 3 else "local-production-low-sample"
        )
        observation_count = len(production)
        evidence = [str(request.observation_path)]
    elif probes:
        per_candidate = mean(float(item["duration_seconds"]) for item in probes)
        confidence = "local-probe"
        observation_count = len(probes)
        evidence = [str(request.observation_path)]
    elif entry:
        per_candidate = float(entry["seconds_per_candidate"][request.resolved.profile.family])
        per_candidate *= max(0.1, megapixels / float(knowledge["reference_megapixels"]))
        confidence = str(entry["confidence"])
        observation_count = 0
        evidence = list(entry.get("evidence", ()))
    else:
        per_candidate = max(0.25, megapixels)
        confidence = "low"
        observation_count = 0
        evidence = []
    effective_workers = max(1.0, request.workers * (0.82 if request.workers > 1 else 1.0))
    expected = per_candidate * request.resolved.profile.run.num_images / effective_workers
    bands = {
        "high": (0.85, 1.25),
        "medium": (0.70, 1.55),
        "local-observation": (0.75, 1.45),
        "local-production": (0.85, 1.20),
        "local-production-low-sample": (0.60, 1.75),
        "local-production-cross-worker": (0.50, 2.00),
        "local-probe": (0.75, 1.50),
        "low": (0.50, 2.50),
    }
    low, high = bands.get(confidence, bands["low"])
    return {
        "lower_seconds": round(expected * low, 3),
        "expected_seconds": round(expected, 3),
        "upper_seconds": round(expected * high, 3),
        "confidence": confidence,
        "seconds_per_candidate": round(per_candidate, 6),
        "evidence": evidence,
        "observation_count": observation_count,
        "model": "paired-profile-plus-local-observations-v1",
    }


def run_preflight(
    request: PreflightRequest,
    *,
    probe_runner: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if request.workers < 1:
        raise ValueError("workers must be >= 1")
    knowledge = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    metadata = _appearance_metadata(request.resolved)
    environment = environment_class()
    observations, observation_warnings = read_matching_observations(
        request.observation_path, request.resolved, request.workers, environment
    )
    entry = knowledge["profiles"].get(metadata.get("id"))
    expensive_or_weak = metadata.get("performance_risk") == "confirmation" or not entry or entry.get("confidence") == "low"
    probe_triggered = bool(expensive_or_weak and not observations and probe_runner is not None)
    probe_measurements: list[dict[str, Any]] = []
    if probe_triggered:
        probe_measurements = list(probe_runner())
        if not probe_measurements or len(probe_measurements) > 3:
            raise ValueError("Preflight probe must return one to three measured candidate observations")
        for item in probe_measurements:
            if float(item.get("duration_seconds", 0)) <= 0:
                raise ValueError("Probe observations require a positive duration_seconds")
        _append_observations(request.observation_path, request, environment, probe_measurements)
        observations = [{"kind": "probe", **item} for item in probe_measurements]
    runtime = _runtime_estimate(request, metadata, observations, knowledge)
    if probe_triggered:
        runtime["confidence"] = "local-probe"
    warning_codes = list(dict.fromkeys(str(code) for code in metadata.get("warning_codes", ())))
    required = warning_codes if metadata.get("performance_risk") == "confirmation" else []
    warnings = [
        {
            "code": code,
            "severity": "warning" if code in required else "info",
            "requires_acknowledgement": code in required,
            "evidence": list(metadata.get("evidence", ())),
        }
        for code in warning_codes
    ]
    warnings.extend(observation_warnings)
    production_count = sum(item.get("kind") == "production" for item in observations)
    if 0 < production_count < 3:
        warnings.append(
            {
                "code": "LOCAL_OBSERVATION_LOW_SAMPLE",
                "severity": "info",
                "requires_acknowledgement": False,
                "evidence": [str(request.observation_path)],
            }
        )
    production_values = [float(item["seconds_per_candidate"]) for item in observations if item.get("kind") == "production"]
    if len(production_values) >= 2 and max(production_values) / max(min(production_values), 1e-9) > 4:
        warnings.append(
            {
                "code": "LOCAL_OBSERVATION_OUT_OF_RANGE",
                "severity": "info",
                "requires_acknowledgement": False,
                "evidence": [str(request.observation_path)],
            }
        )
    disk = estimate_disk(request.output_dir, request.resolved)
    validation = [] if disk["sufficient"] else ["INSUFFICIENT_DISK_SPACE"]
    binding = {
        "contract_hash": request.resolved.contract_hash,
        "num_images": request.resolved.profile.run.num_images,
        "dimensions": list(request.resolved.profile.output.image_size),
        "workers": request.workers,
        "warning_codes": required,
        "evidence_version": knowledge["evidence_version"],
        "environment_class": environment,
    }
    return {
        "schema_version": 1,
        "status": "valid" if not validation else "invalid",
        "validation_errors": validation,
        "profile": metadata.get("id"),
        "warnings": warnings,
        "required_acknowledgements": required,
        "runtime": runtime,
        "disk": disk,
        "probe": {
            "triggered": probe_triggered,
            "warmups": 1 if probe_triggered else 0,
            "measurements": len(probe_measurements),
        },
        "receipt_binding": {"value": binding, "hash": _stable_hash(binding)},
    }


def confirm_preflight(result: dict[str, Any], destination: str | Path) -> dict[str, Any]:
    if result.get("status") != "valid":
        raise ValueError("Cannot confirm an invalid preflight")
    receipt = {
        "schema_version": 1,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "binding_hash": result["receipt_binding"]["hash"],
        "acknowledged_warning_codes": list(result["required_acknowledgements"]),
        "binding": result["receipt_binding"]["value"],
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return receipt


def require_warning_receipt(result: dict[str, Any], receipt_path: str | Path | None) -> None:
    required = list(result.get("required_acknowledgements", ()))
    if not required:
        return
    if receipt_path is None:
        raise ValueError("This configuration requires a matching preflight warning receipt")
    path = Path(receipt_path)
    if not path.exists():
        raise ValueError(f"Preflight warning receipt does not exist: {path}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (
        receipt.get("binding_hash") != result["receipt_binding"]["hash"]
        or receipt.get("acknowledged_warning_codes") != required
    ):
        raise ValueError("Preflight warning receipt does not match the resolved contract or run settings")
