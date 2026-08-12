from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .annotation_evidence import decode_mask_evidence, polygonize_coverage
from .inspection import inspect_pool
from .split_planning import plan_asset_disjoint_splits


@dataclass(frozen=True)
class ExportOptions:
    strategy: str = "random"
    splits: dict[str, float] | None = None
    preserve_names: bool = False
    seed: int = 42
    task: str = "detection"
    mask_semantics: str = "family"
    analyze_only: bool = False


def parse_splits(value: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in value.split(","):
        name, raw = item.split("=", 1)
        result[name.strip()] = float(raw)
    if not result or any(weight <= 0 for weight in result.values()):
        raise ValueError("Splits must contain positive name=weight entries")
    total = sum(result.values())
    return {name: weight / total for name, weight in result.items()}


def _load_pool(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    samples = [json.loads(line) for line in (path / "samples.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return run, samples


def _manifest_hash(path: Path) -> str:
    return hashlib.sha256((path / "run.json").read_bytes()).hexdigest()


def _pool_identity(index: int, run: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "pool_id": f"pool-{index:03d}",
        "run_id": run.get("run_id"),
        "schema_version": int(run.get("schema_version", 1)),
        "contract_hash": run.get("contract_hash"),
        "catalog_fingerprint": run.get("catalog_fingerprint"),
        "run_manifest_sha256": _manifest_hash(path),
    }


def _effective_semantics(requested: str, run: dict[str, Any]) -> str:
    if requested in {"visible", "full"}:
        return requested
    if requested != "family":
        raise ValueError(f"Unsupported mask semantics: {requested}")
    return str(run.get("annotation_policy", {}).get("default_mask_semantics", "visible"))


def _segmentation_lines(
    sample: dict[str, Any],
    source_pool: Path,
    run: dict[str, Any],
    class_ids: dict[str, int],
    requested_semantics: str,
) -> tuple[list[str], list[dict[str, Any]], str]:
    evidence = sample.get("mask_evidence")
    if not isinstance(evidence, dict) or not evidence.get("path"):
        raise ValueError(f"Pool schema v2 sample {sample.get('sample_id')} lacks mask evidence")
    decoded = decode_mask_evidence((source_pool / evidence["path"]).read_bytes(), evidence)
    width, height = (int(value) for value in evidence["image_size"])
    threshold = int(evidence["alpha_threshold"])
    semantics = _effective_semantics(requested_semantics, run)
    lines: list[str] = []
    findings: list[dict[str, Any]] = []
    for annotation in sample.get("annotations", []):
        instance_id = str(annotation.get("instance_id", ""))
        if instance_id not in decoded:
            raise ValueError(f"Mask evidence is missing annotation instance {instance_id}")
        projection = polygonize_coverage(decoded[instance_id][semantics], alpha_threshold=threshold)
        coordinates = " ".join(
            f"{min(1.0, max(0.0, x / width)):.6f} {min(1.0, max(0.0, y / height)):.6f}"
            for x, y in projection.polygon
        )
        lines.append(f"{class_ids[annotation['class_name']]} {coordinates}")
        findings.append(
            {
                "instance_id": instance_id,
                "semantics": semantics,
                "iou": projection.iou,
                "area_error": projection.area_error,
                "points": len(projection.polygon),
                "components": projection.components,
                "holes": projection.holes,
                "status": projection.status,
                "warnings": list(projection.warnings),
            }
        )
    return lines, findings, semantics


def _hash_value(value: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _split_for_fraction(value: float, splits: dict[str, float]) -> str:
    cumulative = 0.0
    for name, fraction in splits.items():
        cumulative += fraction
        if value < cumulative:
            return name
    return next(reversed(splits))


def _assign_random(samples: list[dict[str, Any]], splits: dict[str, float], seed: int) -> dict[str, str]:
    return {sample["_key"]: _split_for_fraction(_hash_value(sample["_key"], seed), splits) for sample in samples}


def _assign_stratified(samples: list[dict[str, Any]], splits: dict[str, float], seed: int) -> dict[str, str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        classes = sorted({annotation["class_name"] for annotation in sample.get("annotations", [])})
        key = "|".join(classes) or "__negative__"
        grouped.setdefault(key, []).append(sample)
    assignments: dict[str, str] = {}
    split_names = list(splits)
    targets = [splits[name] for name in split_names]
    for key, group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda sample: _hash_value(f"{key}:{sample['sample_id']}", seed))
        counts = [0] * len(split_names)
        for sample in ordered:
            index = min(range(len(split_names)), key=lambda idx: counts[idx] / max(targets[idx], 1e-9))
            assignments[sample["_key"]] = split_names[index]
            counts[index] += 1
    return assignments


def export_pools(
    pool_paths: list[str | Path], output_dir: str | Path | None, options: ExportOptions | None = None
) -> dict[str, Any]:
    options = options or ExportOptions()
    if options.task not in {"detection", "segmentation"}:
        raise ValueError(f"Unsupported YOLO task: {options.task}")
    splits = options.splits or {"train": 0.8, "val": 0.1, "test": 0.1}
    if options.analyze_only and options.strategy != "asset-disjoint":
        raise ValueError("Analyze-only mode currently requires --strategy asset-disjoint")
    if not options.analyze_only and output_dir is None:
        raise ValueError("--output-dir is required unless --analyze-only is used")
    output = Path(output_dir).resolve() if output_dir is not None else None
    if output is not None and output.exists() and any(output.iterdir()):
        raise ValueError(f"Export output directory is not empty: {output}")
    pools: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]] = []
    identities: list[dict[str, Any]] = []
    classes: list[str] = []
    for pool_index, raw_path in enumerate(pool_paths):
        path = Path(raw_path).resolve()
        inspection = inspect_pool(path)
        if inspection["status"] != "valid":
            codes = ", ".join(item["code"] for item in inspection["findings"])
            raise ValueError(f"Source pool failed inspection before export: {codes}")
        run, samples = _load_pool(path)
        if options.task == "segmentation" and int(run.get("schema_version", 1)) != 2:
            raise ValueError("YOLO segmentation export requires pool schema v2 mask evidence; pool-v1 remains detection-only")
        pools.append((path, run, samples))
        identities.append(_pool_identity(pool_index, run, path))
        for class_name in run["family"]["classes"]:
            if class_name not in classes:
                classes.append(class_name)
    class_ids = {name: index for index, name in enumerate(classes)}
    all_samples = [
        dict(sample, _pool=str(path), _pool_index=pool_index, _run=run, _key=f"{pool_index}:{sample['sample_id']}")
        for pool_index, (path, run, samples) in enumerate(pools)
        for sample in samples
    ]
    split_plan: dict[str, Any] | None = None
    if options.strategy == "random":
        assignments = _assign_random(all_samples, splits, options.seed)
    elif options.strategy == "stratified":
        assignments = _assign_stratified(all_samples, splits, options.seed)
    elif options.strategy == "asset-disjoint":
        split_plan = plan_asset_disjoint_splits(all_samples, splits, options.seed)
        assignments = split_plan["assignments"]
    else:
        raise ValueError(f"Unsupported export split strategy: {options.strategy}")
    if options.analyze_only:
        assert split_plan is not None
        return {
            "schema_version": 1,
            "status": "complete_with_warnings" if split_plan["analysis"]["warnings"] else "complete",
            "mode": "analyze-only",
            "strategy": options.strategy,
            "splits": splits,
            "source_pools": identities,
            "split_analysis": {
                "schema_version": split_plan["schema_version"],
                "selected_policy": split_plan["selected_policy"],
                "analysis": split_plan["analysis"],
                "comparisons": split_plan["comparisons"],
            },
        }
    assert output is not None
    output.mkdir(parents=True, exist_ok=True)
    counts = {name: 0 for name in splits}
    exported: list[dict[str, Any]] = []
    fidelity_findings: list[dict[str, Any]] = []
    effective_semantics: set[str] = set()
    used_filenames: set[str] = set()
    for index, sample in enumerate(sorted(all_samples, key=lambda item: item["_key"])):
        split = assignments[sample["_key"]]
        counts[split] += 1
        source_pool = Path(sample["_pool"])
        source_image = source_pool / sample["image_path"]
        extension = source_image.suffix
        filename = source_image.name if options.preserve_names else f"image_{index:08d}{extension}"
        if filename in used_filenames:
            filename = f"{source_image.stem}_pool{sample['_pool_index']}{extension}"
        used_filenames.add(filename)
        image_dir = output / "images" / split
        label_dir = output / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image, image_dir / filename)
        if options.task == "segmentation":
            lines, sample_fidelity, semantics = _segmentation_lines(
                sample, source_pool, sample["_run"], class_ids, options.mask_semantics
            )
            effective_semantics.add(semantics)
            for finding in sample_fidelity:
                fidelity_findings.append({"sample_id": sample["sample_id"], **finding})
        else:
            lines = []
            for annotation in sample.get("annotations", []):
                cx, cy, width, height = annotation["normalized_bbox"]
                lines.append(f"{class_ids[annotation['class_name']]} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
        (label_dir / f"{Path(filename).stem}.txt").write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
        exported.append(
            {
                "sample_id": sample["sample_id"],
                "pool_sample_key": sample["_key"],
                "split": split,
                "filename": filename,
                "source_pool_id": identities[int(sample["_pool_index"])]["pool_id"],
            }
        )
    data = {"path": ".", "train": "images/train", "val": "images/val", "test": "images/test", "names": {index: name for index, name in enumerate(classes)}}
    (output / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    summary = {
        "schema_version": 1,
        "status": "complete_with_warnings"
        if any(item["warnings"] for item in fidelity_findings)
        or bool(split_plan and split_plan["analysis"]["warnings"])
        else "complete",
        "format": "yolo",
        "task": options.task,
        "requested_mask_semantics": options.mask_semantics if options.task == "segmentation" else None,
        "mask_semantics": (next(iter(effective_semantics)) if len(effective_semantics) == 1 else "mixed") if options.task == "segmentation" else None,
        "strategy": options.strategy,
        "splits": splits,
        "split_counts": counts,
        "classes": classes,
        "source_pools": identities,
        "split_analysis": (
            {
                "schema_version": split_plan["schema_version"],
                "selected_policy": split_plan["selected_policy"],
                "analysis": split_plan["analysis"],
                "comparisons": split_plan["comparisons"],
            }
            if split_plan
            else None
        ),
        "samples": exported,
        "fidelity": {
            "instances": len(fidelity_findings),
            "minimum_iou": min((item["iou"] for item in fidelity_findings), default=None),
            "maximum_area_error": max((item["area_error"] for item in fidelity_findings), default=None),
            "warning_instances": sum(bool(item["warnings"]) for item in fidelity_findings),
            "findings": fidelity_findings,
        } if options.task == "segmentation" else None,
    }
    (output / "export.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
