from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExportOptions:
    strategy: str = "random"
    splits: dict[str, float] | None = None
    preserve_names: bool = False
    seed: int = 42


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


def _assign_asset_disjoint(samples: list[dict[str, Any]], splits: dict[str, float], seed: int) -> dict[str, str]:
    parent = list(range(len(samples)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    asset_owner: dict[str, int] = {}
    for index, sample in enumerate(samples):
        assets = [str(annotation["source_asset"]) for annotation in sample.get("annotations", [])]
        assets.extend(str(asset) for asset in sample.get("background", {}).get("sources", []))
        for asset in assets:
            if asset in asset_owner:
                union(index, asset_owner[asset])
            else:
                asset_owner[asset] = index
    groups: dict[int, list[int]] = {}
    for index in range(len(samples)):
        groups.setdefault(find(index), []).append(index)
    assignments: dict[str, str] = {}
    for indices in groups.values():
        key = "|".join(sorted(samples[index]["_key"] for index in indices))
        split = _split_for_fraction(_hash_value(key, seed), splits)
        for index in indices:
            assignments[samples[index]["_key"]] = split
    return assignments


def export_pools(pool_paths: list[str | Path], output_dir: str | Path, options: ExportOptions | None = None) -> dict[str, Any]:
    options = options or ExportOptions()
    splits = options.splits or {"train": 0.8, "val": 0.1, "test": 0.1}
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Export output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    pools: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]] = []
    classes: list[str] = []
    for raw_path in pool_paths:
        path = Path(raw_path).resolve()
        run, samples = _load_pool(path)
        pools.append((path, run, samples))
        for class_name in run["family"]["classes"]:
            if class_name not in classes:
                classes.append(class_name)
    class_ids = {name: index for index, name in enumerate(classes)}
    all_samples = [
        dict(sample, _pool=str(path), _pool_index=pool_index, _key=f"{pool_index}:{sample['sample_id']}")
        for pool_index, (path, _run, samples) in enumerate(pools)
        for sample in samples
    ]
    if options.strategy == "random":
        assignments = _assign_random(all_samples, splits, options.seed)
    elif options.strategy == "stratified":
        assignments = _assign_stratified(all_samples, splits, options.seed)
    elif options.strategy == "asset-disjoint":
        assignments = _assign_asset_disjoint(all_samples, splits, options.seed)
    else:
        raise ValueError(f"Unsupported export split strategy: {options.strategy}")
    counts = {name: 0 for name in splits}
    exported: list[dict[str, Any]] = []
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
                "source_pool": str(source_pool),
            }
        )
    data = {"path": str(output), "train": "images/train", "val": "images/val", "test": "images/test", "names": {index: name for index, name in enumerate(classes)}}
    (output / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    summary = {
        "schema_version": 1,
        "status": "complete",
        "format": "yolo",
        "strategy": options.strategy,
        "splits": splits,
        "split_counts": counts,
        "classes": classes,
        "source_pools": [str(Path(path).resolve()) for path in pool_paths],
        "samples": exported,
    }
    (output / "export.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
