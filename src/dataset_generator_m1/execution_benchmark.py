"""Portable production-path comparisons, with isolated observations and bounded policies."""
import json
from pathlib import Path
from time import perf_counter

from .config import load_yaml_strict
from .generator import GenerationOptions, generate_pool
from .identities import digest, generation_identity, software_identity
from .assets import build_asset_catalog
from .inspection import inspect_pool
from .models import ExecutionConfig, GenerationProfile
from .execution import plan_execution
from .preparation import PreparationRequest, prepare_generation
from .renderer_version import derived_profile_payload


def _signature(root: Path) -> str:
    records = [json.loads(line) for line in (root / "samples.jsonl").read_text().splitlines() if line]
    return digest([{"geometry": row["geometry_signature"], "annotations": row["annotations"],
                    "masks": {k: v for k, v in row["mask_evidence"].items() if k != "path"}}
                   for row in records])


def production_benchmark(resolved, output_dir, *, matrix_file=None, samples=20, repeats=3, warmup=1):
    if samples < 1 or repeats < 1 or warmup < 0:
        raise ValueError("Benchmark samples/repeats must be positive and warmup non-negative")
    if matrix_file:
        matrix = load_yaml_strict(matrix_file)
        if set(matrix) != {"schema_version", "variants"} or matrix["schema_version"] != 1 or not isinstance(matrix["variants"], dict):
            raise ValueError("Execution matrix requires schema_version: 1 and variants mapping")
    else:
        matrix = {"variants": {"configured": {}}}
    variants = {}
    import re
    for name, changes in matrix["variants"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) or not isinstance(changes, dict):
            raise ValueError("Execution variant names and policies must be valid mappings")
        variants[name] = ExecutionConfig.model_validate({**resolved.profile.execution.model_dump(), **changes})
    if not variants:
        raise ValueError("Execution matrix must not be empty")
    root = Path(output_dir)
    if root.exists():
        raise ValueError("Benchmark destination must not exist")
    # Validate every policy and catalog before creating any benchmark output.
    catalog = build_asset_catalog(resolved)
    for policy in variants.values():
        plan_execution(resolved.model_copy(update={"profile": resolved.profile.model_copy(update={"execution": policy})}))
    records = []
    reference = None
    for repeat in range(repeats):
        ordered = list(variants)
        ordered = ordered[repeat % len(ordered):] + ordered[:repeat % len(ordered)]
        for name in ordered:
            policy = variants[name]
            payload = resolved.profile.model_dump(mode="json")
            payload["execution"] = policy.model_dump(mode="json")
            payload["run"]["num_images"] = samples
            profile = GenerationProfile.model_validate(payload)
            current = resolved.model_copy(update={"profile": profile,
                "contract_hash": digest({"base": resolved.contract_hash, "benchmark_profile": derived_profile_payload(payload)}),
                "applied_overrides": {**resolved.applied_overrides, "benchmark.execution": policy.model_dump(), "benchmark.samples": samples}})
            plan = plan_execution(current)
            pool = root / f"{repeat:02d}-{name}"
            prepared = prepare_generation(PreparationRequest(current, pool, plan.workers, root / "local-observations.jsonl"))
            # Separate warm-up pools exercise process startup, masks, writes and QA too.
            if warmup:
                warm_profile = current.profile.model_copy(update={"run": current.profile.run.model_copy(update={"num_images": warmup})})
                warm = current.model_copy(update={"profile": warm_profile, "contract_hash": digest({"base": current.contract_hash, "warmup": warmup})})
                warm_pool = root / f"warmup-{repeat:02d}-{name}"
                warm_prepared = prepare_generation(PreparationRequest(warm, warm_pool, plan.workers, root / "local-observations.jsonl"))
                generate_pool(warm, warm_pool, GenerationOptions(display="quiet", prepared=warm_prepared))
            started = perf_counter()
            summary = generate_pool(current, pool, GenerationOptions(display="quiet", prepared=prepared))
            wall = perf_counter() - started
            inspection = inspect_pool(pool)
            signature = _signature(pool)
            if reference is None:
                reference = signature
            if reference != signature:
                raise RuntimeError("Execution policies changed geometry/annotation/mask evidence")
            records.append({"variant": name, "repeat": repeat, "status": summary["status"],
                "inspection": inspection["status"], "content_signature": signature,
                "generation_identity": generation_identity(current, catalog), "execution": plan.as_dict(),
                "wall_seconds": wall, "active_seconds": summary["elapsed_seconds"],
                "accepted": summary["accepted_samples"], "attempts": summary["candidate_attempts"],
                "throughput": summary["throughput_images_per_second"], "stage_work": summary["stage_timings"],
                "resource_peaks": summary["resource_peaks"]})
    result = {"schema_version": 1, "status": "complete" if all(r["status"] == "complete" and r["inspection"] == "valid" for r in records) else "failed",
        "scope": "environment-local production path; no machine-independent thresholds", "software": software_identity(),
        "warmup_samples_per_variant": warmup, "samples": samples, "repeats": repeats,
        "low_sample": repeats < 3 or samples < 20, "records": records}
    (root / "benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
