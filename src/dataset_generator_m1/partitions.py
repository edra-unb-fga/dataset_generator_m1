"""Plan and verify source isolation before paying for scene generation."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .split_planning import _greedy_assign


def manifest_digest(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_partition(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("sha256") != manifest_digest(value):
        raise ValueError("Invalid source partition manifest or digest")
    if value.get("policy") not in {"asset-disjoint", "background-disjoint"}:
        raise ValueError("Unsupported source partition policy")
    if not isinstance(value.get("assignments"), dict) or set(value["assignments"]) != {"foreground", "background"}:
        raise ValueError("Partition manifest requires foreground and background assignments")
    splits = value.get("splits")
    if not isinstance(splits, dict) or not splits or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in splits.values()):
        raise ValueError("Invalid partition split weights")
    for role, assignments in value["assignments"].items():
        if not isinstance(assignments, dict) or not assignments:
            raise ValueError("Partition role assignments must be nonempty objects")
        allowed = set(splits) | ({"shared"} if role == "foreground" and value["policy"] == "background-disjoint" else set())
        if any(not re.fullmatch(r"[0-9a-f]{64}", digest) or split not in allowed for digest, split in assignments.items()):
            raise ValueError("Invalid partition content identity or assignment")
    return value


def plan_source_partitions(catalog: Any, splits: dict[str, float], seed: int, policy: str) -> dict[str, Any]:
    if policy not in {"asset-disjoint", "background-disjoint"}:
        raise ValueError("Source partition policy must be asset-disjoint or background-disjoint")
    if not splits or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in splits.values()):
        raise ValueError("Source partitions need positive split weights")
    total = sum(splits.values())
    splits = {key: value / total for key, value in splits.items()}
    rows = [("background", asset) for asset in catalog.backgrounds]
    if policy == "asset-disjoint":
        rows += [("foreground", asset) for asset in catalog.foregrounds]
    parent = list(range(len(rows)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    owners = {}
    for index, (_, asset) in enumerate(rows):
        keys = ["sha256:" + asset.content_hash]
        if asset.material_id:
            keys.append("material:" + asset.material_id)
        for key in keys:
            if key in owners:
                parent[find(index)] = find(owners[key])
            else:
                owners[key] = index
    groups = {}
    for index in range(len(rows)):
        groups.setdefault(find(index), []).append(rows[index])
    components = []
    for group in groups.values():
        key = "|".join(sorted({asset.content_hash for _, asset in group}))
        components.append({"id": hashlib.sha256(key.encode()).hexdigest(), "key": key, "size": len(group),
                           "classes": dict(Counter(asset.class_name for role, asset in group if role == "foreground")), "rows": group})
    assignments = {"foreground": {}, "background": {}}
    choices = _greedy_assign(components, splits, seed, class_aware=policy == "asset-disjoint")
    for component in components:
        for role, asset in component["rows"]:
            assignments[role][asset.content_hash] = choices[component["id"]]
    if policy == "background-disjoint":
        assignments["foreground"] = {asset.content_hash: "shared" for asset in catalog.foregrounds}
    support = {}
    for split in splits:
        foregrounds = [asset for asset in catalog.foregrounds if assignments["foreground"].get(asset.content_hash) in {split, "shared"}]
        backgrounds = [asset for asset in catalog.backgrounds if assignments["background"].get(asset.content_hash) == split]
        missing = sorted(set(catalog.class_names) - {asset.class_name for asset in foregrounds})
        support[split] = {"foreground_assets": len(foregrounds), "background_assets": len(backgrounds), "missing_classes": missing,
                          "feasible": bool(backgrounds) and not missing}
    result = {"schema_version": 1, "policy": policy, "seed": seed, "splits": splits,
              "catalog_fingerprint": catalog.fingerprint, "assignments": assignments,
              "support": support, "feasible": all(item["feasible"] for item in support.values()),
              "guarantee": "source-content-and-known-material-groups" if policy == "background-disjoint" else "all-source-content-and-known-material-groups",
              "shared_foreground_identities": sorted(assignments["foreground"]) if policy == "background-disjoint" else [],
              "limitations": ["Unknown derivative relationships cannot be inferred from pixels.", "Source support is not a guarantee of scene acceptance or exact image counts."]}
    result["status"] = "complete" if result["feasible"] else "infeasible"
    result["sha256"] = manifest_digest(result)
    return result
