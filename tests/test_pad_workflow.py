import json
from pathlib import Path

import pytest

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.families import family_names
from dataset_generator_m1.generator import GenerationOptions, generate_pool
from dataset_generator_m1.inspection import inspect_pool
from dataset_generator_m1.exporter import ExportOptions, export_pools
from helpers import write_derived_composer


def test_pad_task_uses_shared_generation_masks_and_both_exports(tmp_path: Path):
    assert "landing-pad" in family_names()
    config = write_derived_composer(tmp_path, "landing-pad", {
        "run": {"num_images": 2, "max_candidate_attempts": 5},
        "output": {"image_size": [160, 120], "image_format": "png"},
        "sampling": {"instances_per_image": [2, 2], "foreground_size": [0.12, 0.12], "count_policy": "require-count"},
        "reporting": {"qa_samples": 1},
        "background_mixing": {"recipe_weights": {"direct": 1.0}},
    })
    resolved = load_profile(config)
    records = []
    for workers in (1, 2):
        pool = tmp_path / f"pool-{workers}"
        result = generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=workers))
        assert result["status"] == "complete"
        assert inspect_pool(pool)["status"] == "valid"
        samples = [json.loads(line) for line in (pool / "samples.jsonl").read_text().splitlines()]
        assert all(len(sample["annotations"]) == 2 for sample in samples)
        assert all(a["class_name"] == "pad" for sample in samples for a in sample["annotations"])
        records.append([(s["geometry_signature"], s["annotations"], s["mask_evidence"]["sha256"]) for s in samples])
        for task in ("detection", "segmentation"):
            export = export_pools([pool], tmp_path / f"{task}-{workers}", ExportOptions(task=task, splits={"train": 1.0}))
            assert export["status"] in {"complete", "complete_with_warnings"}
    assert records[0] == records[1]


@pytest.mark.parametrize("policy", ["best-effort", "require-count"])
def test_count_policy_never_falls_back_silently(tmp_path: Path, policy: str):
    config = write_derived_composer(tmp_path, "landing-pad", {
        "run": {"num_images": 1, "max_candidate_attempts": 2},
        "output": {"image_size": [96, 96], "image_format": "png"},
        "sampling": {"instances_per_image": [20, 20], "foreground_size": [0.8, 0.8], "placement_attempts": 3, "count_policy": policy},
        "background_mixing": {"recipe_weights": {"direct": 1.0}},
    })
    summary = generate_pool(load_profile(config), tmp_path / "pool", GenerationOptions(display="quiet"))
    if policy == "require-count":
        assert summary["accepted_samples"] == 0
        assert summary["status"] == "failed"
    else:
        assert summary["accepted_samples"] <= 1
    assert summary["object_rejections"] > 0
