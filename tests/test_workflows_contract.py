import json
from pathlib import Path

import yaml

from dataset_generator_m1.config import load_profile, load_yaml_strict
from dataset_generator_m1.models import OutputConfig, RunConfig
from dataset_generator_m1.workflows import benchmark, compare_artifacts, preview_backgrounds, preview_scenes
from helpers import write_derived_composer


def small_resolved():
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    profile = resolved.profile.model_copy(
        update={
            "output": OutputConfig(image_size=(160, 96), image_format="png"),
            "run": RunConfig(label="workflow-test", num_images=1, seed=19, max_candidate_attempts=5),
        }
    )
    return resolved.model_copy(update={"profile": profile})


def test_background_preview_and_benchmark_write_audit_artifacts(tmp_path: Path) -> None:
    resolved = small_resolved()

    preview = preview_backgrounds(resolved, tmp_path / "backgrounds", samples_per_recipe=1)
    result = benchmark(resolved, tmp_path / "benchmark", samples=1, warmup=0)

    assert len(preview["samples"]) == len(resolved.recipes.recipes)
    assert all(len(sample["graph_hash"]) == 64 for sample in preview["samples"])
    assert (tmp_path / "backgrounds" / "index.html").exists()
    assert result["stage_timings"]["encoding"]["mean_ns"] > 0
    assert result["stage_timings"]["writing"]["mean_ns"] > 0


def test_scene_variants_share_geometry_and_compare_writes_html(tmp_path: Path) -> None:
    profile_path = write_derived_composer(
        tmp_path,
        "landing",
        {
            "run": {"label": "variant-test", "num_images": 1, "max_candidate_attempts": 5},
            "output": {"image_size": [160, 96], "image_format": "png"},
        },
    )
    variants_path = tmp_path / "variants.yaml"
    variants_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "variants": {
                    "baseline": {},
                    "color": {
                        "appearance": {
                            "final": [
                                {
                                    "type": "RandomBrightnessContrast",
                                    "probability": 1.0,
                                    "params": {"brightness_limit": [-0.1, 0.1], "contrast_limit": [-0.1, 0.1]},
                                }
                            ]
                        }
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = preview_scenes(profile_path, variants_path, tmp_path / "scenes", samples=1)

    baseline = json.loads((tmp_path / "scenes" / "baseline" / "samples.jsonl").read_text(encoding="utf-8"))
    color = json.loads((tmp_path / "scenes" / "color" / "samples.jsonl").read_text(encoding="utf-8"))
    assert baseline["geometry_signature"] == color["geometry_signature"]
    assert baseline["annotations"] == color["annotations"]
    comparison = compare_artifacts(
        tmp_path / "scenes" / "baseline" / "summary.json",
        tmp_path / "scenes" / "color" / "summary.json",
        tmp_path / "comparison",
    )
    assert result["status"] == comparison["status"] == "complete"
    assert (tmp_path / "comparison" / "index.html").exists()
