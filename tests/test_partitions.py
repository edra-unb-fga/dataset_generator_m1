import json
from pathlib import Path

import pytest

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.config import load_profile, load_yaml_strict
from dataset_generator_m1.partitions import plan_source_partitions
from dataset_generator_m1.configurator import save_composer
from dataset_generator_m1.generator import generate_pool, GenerationOptions
from dataset_generator_m1.exporter import export_pools, ExportOptions
from dataset_generator_m1.split_planning import plan_asset_disjoint_splits


def test_background_partitions_are_portable_and_consumed_before_generation(tmp_path: Path):
    resolved = load_profile("examples/configs/landing-pad_minimal.yaml")
    catalog = build_asset_catalog(resolved)
    manifest = plan_source_partitions(catalog, {"train": 0.5, "val": 0.5}, 42, "background-disjoint")
    assert manifest["feasible"] is True
    assert manifest == plan_source_partitions(catalog, {"train": 0.5, "val": 0.5}, 42, "background-disjoint")
    path = tmp_path / "partition.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    pools = []
    hashes = []
    for split in manifest["splits"]:
        doc = load_yaml_strict("examples/configs/landing-pad_minimal.yaml")
        doc["inline"] = {"assets": {**resolved.profile.assets.model_dump(mode="json"), "partition": {"manifest_file": str(path), "split": split}},
                         "run": {"num_images": 1}, "output": {"image_size": [96, 96]}, "reporting": {"qa_samples": 0},
                         "background_mixing": {"recipe_weights": {"direct": 1.0}}}
        config = save_composer(doc, tmp_path / f"{split}.yaml")
        current = load_profile(config)
        hashes.append({a.content_hash for a in build_asset_catalog(current).backgrounds})
        pool = tmp_path / split
        assert generate_pool(current, pool, GenerationOptions(display="quiet"))["status"] == "complete"
        pools.append(pool)
    assert not hashes[0] & hashes[1]
    for task in ("detection", "segmentation"):
        result = export_pools(pools, tmp_path / task, ExportOptions(task=task, strategy="background-disjoint", splits=manifest["splits"]))
        assert {row["split"] for row in result["samples"]} == {"train", "val"}
        assert result["split_analysis"]["analysis"]["pre_generation"] is True
    samples = [json.loads((pool / "samples.jsonl").read_text()) for pool in pools]
    for i, sample in enumerate(samples):
        sample["_key"] = str(i)
    plan = plan_asset_disjoint_splits(samples, manifest["splits"], 42, policy="background-disjoint")
    assert plan["analysis"]["component_count"] == 2


def test_strict_pad_partition_reports_insufficient_independent_artwork():
    catalog = build_asset_catalog(load_profile("examples/configs/landing-pad_minimal.yaml"))
    result = plan_source_partitions(catalog, {"train": .8, "val": .1, "test": .1}, 42, "asset-disjoint")
    assert result["feasible"] is False
    assert any(row["missing_classes"] for row in result["support"].values())


def test_missing_background_lineage_cannot_claim_isolation():
    with pytest.raises(ValueError, match="lineage"):
        plan_asset_disjoint_splits([{"_key": "empty", "annotations": []}], {"train": 1.0}, 42)
