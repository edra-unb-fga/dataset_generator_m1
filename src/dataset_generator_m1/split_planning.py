from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any


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


def _sample_assets(sample: dict[str, Any]) -> tuple[str, ...]:
    assets = {str(annotation["source_asset"]) for annotation in sample.get("annotations", [])}
    assets.update(str(asset) for asset in sample.get("background", {}).get("sources", []))
    return tuple(sorted(assets))


def _components(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    owners: dict[str, int] = {}
    for index, sample in enumerate(samples):
        for asset in _sample_assets(sample):
            if asset in owners:
                union(index, owners[asset])
            else:
                owners[asset] = index
    groups: dict[int, list[int]] = {}
    for index in range(len(samples)):
        groups.setdefault(find(index), []).append(index)
    result: list[dict[str, Any]] = []
    for indices in groups.values():
        keys = sorted(str(samples[index]["_key"]) for index in indices)
        class_counts: Counter[str] = Counter()
        assets: set[str] = set()
        negatives = 0
        for index in indices:
            annotations = samples[index].get("annotations", [])
            if not annotations:
                negatives += 1
            class_counts.update(str(item["class_name"]) for item in annotations)
            assets.update(_sample_assets(samples[index]))
        result.append(
            {
                "id": hashlib.sha256("|".join(keys).encode("utf-8")).hexdigest()[:12],
                "key": "|".join(keys),
                "indices": tuple(indices),
                "size": len(indices),
                "classes": dict(sorted(class_counts.items())),
                "assets": tuple(sorted(assets)),
                "negative_samples": negatives,
            }
        )
    return sorted(result, key=lambda item: item["id"])


def _hash_assign(components: list[dict[str, Any]], splits: dict[str, float], seed: int) -> dict[str, str]:
    return {item["id"]: _split_for_fraction(_hash_value(item["key"], seed), splits) for item in components}


def _greedy_assign(
    components: list[dict[str, Any]], splits: dict[str, float], seed: int, *, class_aware: bool
) -> dict[str, str]:
    names = list(splits)
    total_samples = sum(item["size"] for item in components)
    target_samples = {name: total_samples * splits[name] for name in names}
    class_totals: Counter[str] = Counter()
    for component in components:
        class_totals.update(component["classes"])
    sample_counts = Counter({name: 0 for name in names})
    class_counts = {name: Counter() for name in names}
    assignments: dict[str, str] = {}
    ordered = sorted(components, key=lambda item: (-item["size"], _hash_value(item["key"], seed), item["id"]))
    for component in ordered:
        def score(name: str) -> tuple[float, float, str]:
            proposed_samples = sample_counts[name] + component["size"]
            sample_error = abs(proposed_samples - target_samples[name]) / max(total_samples, 1)
            class_error = 0.0
            if class_aware:
                for class_name, count in component["classes"].items():
                    target = class_totals[class_name] * splits[name]
                    class_error += abs(class_counts[name][class_name] + count - target) / max(class_totals[class_name], 1)
            return sample_error + class_error, sample_counts[name] / max(splits[name], 1e-9), name

        selected = min(names, key=score)
        assignments[component["id"]] = selected
        sample_counts[selected] += component["size"]
        class_counts[selected].update(component["classes"])
    return assignments


def _comparison(
    components: list[dict[str, Any]], assignments: dict[str, str], splits: dict[str, float]
) -> dict[str, Any]:
    total = sum(item["size"] for item in components)
    counts = Counter({name: 0 for name in splits})
    class_counts = {name: Counter() for name in splits}
    for component in components:
        split = assignments[component["id"]]
        counts[split] += component["size"]
        class_counts[split].update(component["classes"])
    requested = {name: total * fraction for name, fraction in splits.items()}
    deviations = {name: counts[name] - requested[name] for name in splits}
    return {
        "sample_counts": dict(counts),
        "requested_sample_counts": requested,
        "sample_deviation": deviations,
        "l1_fraction_deviation": sum(abs(value) for value in deviations.values()) / max(total, 1),
        "maximum_fraction_deviation": max((abs(value) for value in deviations.values()), default=0.0) / max(total, 1),
        "class_counts": {name: dict(sorted(values.items())) for name, values in class_counts.items()},
    }


def plan_asset_disjoint_splits(
    samples: list[dict[str, Any]], splits: dict[str, float], seed: int
) -> dict[str, Any]:
    """Analyze source-connected components and return the unchanged hash assignment plus alternatives."""
    components = _components(samples)
    nonempty_splits = sum(fraction > 0 for fraction in splits.values())
    class_support: dict[str, dict[str, int]] = {}
    all_classes = sorted({name for component in components for name in component["classes"]})
    for class_name in all_classes:
        class_support[class_name] = {
            "sample_support": sum(component["classes"].get(class_name, 0) for component in components),
            "component_support": sum(class_name in component["classes"] for component in components),
        }
    warnings: list[dict[str, Any]] = []
    if len(components) < nonempty_splits:
        warnings.append(
            {
                "code": "ASSET_DISJOINT_SPLITS_IMPOSSIBLE",
                "message": f"{len(components)} source components cannot populate {nonempty_splits} requested splits.",
            }
        )
    for class_name, support in class_support.items():
        if support["component_support"] < nonempty_splits:
            warnings.append(
                {
                    "code": "CLASS_PARTITION_FRAGILE",
                    "class_name": class_name,
                    "component_support": support["component_support"],
                    "requested_splits": nonempty_splits,
                }
            )
    fragile_classes = sorted(
        name for name, support in class_support.items() if support["component_support"] < nonempty_splits
    )
    assignment_sets = {
        "hash": _hash_assign(components, splits, seed),
        "greedy-sample": _greedy_assign(components, splits, seed, class_aware=False),
        "greedy-class": _greedy_assign(components, splits, seed, class_aware=True),
    }
    selected_components = assignment_sets["hash"]
    sample_assignments = {
        str(samples[index]["_key"]): selected_components[component["id"]]
        for component in components
        for index in component["indices"]
    }
    public_components = [
        {
            "component_id": item["id"],
            "size": item["size"],
            "asset_count": len(item["assets"]),
            "classes": item["classes"],
            "negative_samples": item["negative_samples"],
        }
        for item in sorted(components, key=lambda value: (-value["size"], value["id"]))
    ]
    comparisons = {
        name: _comparison(components, assignments, splits)
        for name, assignments in assignment_sets.items()
    }
    selected_deviation = comparisons["hash"]["sample_deviation"]
    if any(abs(value) >= 1.0 for value in selected_deviation.values()):
        warnings.append(
            {
                "code": "HASH_ASSIGNMENT_IMBALANCED",
                "message": "The current deterministic hash assignment differs from requested split counts by at least one sample.",
                "sample_deviation": selected_deviation,
            }
        )
    return {
        "schema_version": 1,
        "selected_policy": "hash",
        "assignments": sample_assignments,
        "analysis": {
            "sample_count": len(samples),
            "component_count": len(components),
            "component_sizes": sorted((item["size"] for item in components), reverse=True),
            "components": public_components,
            "classes": class_support,
            "negative_samples": sum(not sample.get("annotations") for sample in samples),
            "requested_splits": splits,
            "feasibility": {
                "all_splits_populatable": len(components) >= nonempty_splits,
                "fragile_classes": fragile_classes,
                "largest_component_fraction": max((item["size"] for item in components), default=0)
                / max(len(samples), 1),
            },
            "warnings": warnings,
        },
        "comparisons": comparisons,
    }
