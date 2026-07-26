from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from dataset_generator_m1.augmentation_study import (
    AugmentationStudyRequest,
    balanced_treatment_order,
    resolve_treatments,
    run_augmentation_study,
    validate_study_artifacts,
)
from dataset_generator_m1.config import load_profile, load_yaml_strict


def _tiny_profile(tmp_path: Path) -> Path:
    raw = load_yaml_strict("examples/configs/manometro_minimal.yaml")
    raw["run"].update({"label": "augmentation-test", "num_images": 1, "max_candidate_attempts": 4})
    raw["output"].update({"image_size": [96, 96], "image_format": "png"})
    raw["sampling"].update({"instances_per_image": [1, 1], "foreground_size": [0.2, 0.2]})
    raw["scene"]["canvas_scale"] = 1.25
    raw["background_synthesis"]["recipe_weights"] = {"direct": 1.0}
    path = tmp_path / "tiny.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def test_balanced_order_contains_each_treatment_once() -> None:
    names = ("a", "b", "c", "d")
    orders = [balanced_treatment_order(names, index) for index in range(8)]
    assert all(set(order) == set(names) and len(order) == len(names) for order in orders)
    assert {order[0] for order in orders} == set(names)


def test_default_matrix_preserves_legacy_provenance() -> None:
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    treatments, metadata = resolve_treatments(resolved)

    assert tuple(treatments) == (
        "no-appearance",
        "current",
        "legacy-heavy-compatible",
        "realistic-heavy-background",
        "realistic-heavy-foreground",
        "realistic-heavy-final",
        "realistic-heavy-combined",
    )
    assert metadata["legacy_source_commit"] == "a3dec1f"
    assert metadata["unsupported_translation"]["source"] == "AtmosphericFog"
    legacy_types = [spec.type for spec in treatments["legacy-heavy-compatible"].final]
    assert "RandomFog" in legacy_types
    assert "AtmosphericFog" not in legacy_types


def test_invalid_matrix_fails_before_output_creation(tmp_path: Path) -> None:
    profile = _tiny_profile(tmp_path)
    matrix = tmp_path / "bad-matrix.yaml"
    matrix.write_text(
        yaml.safe_dump({"schema_version": 1, "geometry": {"image_size": [1, 1]}, "treatments": {"x": {}}}),
        encoding="utf-8",
    )
    output = tmp_path / "partial-output"

    with pytest.raises(ValueError):
        run_augmentation_study(AugmentationStudyRequest(profile, output, matrix=matrix, warmups=0, samples=1))

    assert not output.exists()


def test_small_study_keeps_pair_invariants_and_valid_report(tmp_path: Path) -> None:
    profile = _tiny_profile(tmp_path)
    output = tmp_path / "study"
    result = run_augmentation_study(AugmentationStudyRequest(profile, output, warmups=0, samples=1))

    records = [json.loads(line) for line in (output / "measurements.jsonl").read_text(encoding="utf-8").splitlines()]
    assert result["status"] == "complete"
    assert len(records) == 7
    assert len({record["geometry_signature"] for record in records}) == 1
    assert len({record["annotation_signature"] for record in records}) == 1
    assert len({record["mask_signature"] for record in records}) == 1
    assert all(record["exclusive_renderer_ns"] for record in records)
    assert all(
        record["exclusive_renderer_ns"]["background_effects"]
        == sum(effect["duration_ns"] for effect in record["effects"] if effect["stage"] == "background")
        for record in records
    )
    current = next(record for record in records if record["treatment"] == "current")
    combined = next(record for record in records if record["treatment"] == "realistic-heavy-combined")
    current_params = {effect["id"]: effect["applied_params"] for effect in current["effects"]}
    combined_params = {effect["id"]: effect["applied_params"] for effect in combined["effects"]}
    assert all(combined_params[effect_id] == params for effect_id, params in current_params.items())
    assert result["analysis"]["warnings"]
    assert validate_study_artifacts(output)["status"] == "valid"
    assert (output / "report" / "contact-sheet.jpg").exists()


def test_study_retries_renderer_rejection(monkeypatch, tmp_path: Path) -> None:
    import dataset_generator_m1.augmentation_study as study_module

    profile = _tiny_profile(tmp_path)
    output = tmp_path / "retry-study"
    original = study_module.SceneRenderer.render
    calls = {"count": 0}

    def reject_first(self, plan, background):
        calls["count"] += 1
        if calls["count"] == 1:
            raise study_module.SceneRejected("synthetic qualification rejection")
        return original(self, plan, background)

    monkeypatch.setattr(study_module.SceneRenderer, "render", reject_first)
    result = run_augmentation_study(AugmentationStudyRequest(profile, output, warmups=0, samples=1))

    assert result["status"] == "complete"
    assert calls["count"] >= 9
