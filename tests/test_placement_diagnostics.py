from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from helpers import write_derived_composer

from dataset_generator_m1.placement_diagnostics import (
    bounded_spatial_histogram,
    build_rejection_record,
    summarize_placement_diagnostics,
)


def test_diagnostics_are_bounded_and_summarized_by_declared_dimensions() -> None:
    histogram = bounded_spatial_histogram(
        [(0.05, 0.05), (0.09, 0.06), (0.99, 0.99)], bins=4
    )
    record = build_rejection_record(
        slot=2,
        candidate_attempt=3,
        object_attempt=4,
        asset="root0/landing.png",
        class_name="landing",
        group="gabaritos",
        scale=0.21,
        rotation_degrees=37.0,
        estimated_size=(110.0, 95.0),
        requested_objects=6,
        stage="planner.placement",
        reason="placement_attempts_exhausted",
        placement_attempts=10,
        blocking_counts={"overlap": 10},
        spatial_histogram=histogram,
        best_failed={"bbox": [1.0, 2.0, 10.0, 12.0], "blocking_count": 1},
    )

    summary = summarize_placement_diagnostics([record])

    assert len(record["spatial_histogram"]["counts"]) == 16
    assert sum(record["spatial_histogram"]["counts"]) == 3
    assert summary["total_rejections"] == 1
    assert summary["by_stage"]["planner.placement"]["rejections"] == 1
    assert summary["by_asset"]["root0/landing.png"]["rate"] == 1.0
    assert summary["by_scale_band"]["0.20-0.30"]["rejections"] == 1
    assert summary["by_rotation_band"]["30-45"]["rejections"] == 1
    assert len(json.dumps(record, separators=(",", ":"))) < 1800


def test_spatial_histogram_clamps_edge_coordinates_deterministically() -> None:
    first = bounded_spatial_histogram([(-1, -1), (0.5, 0.5), (2, 2)], bins=3)
    second = bounded_spatial_histogram([(-1, -1), (0.5, 0.5), (2, 2)], bins=3)

    assert first == second
    assert first["counts"][0] == 1
    assert first["counts"][4] == 1
    assert first["counts"][8] == 1


def test_rejected_candidate_retains_object_diagnostics_for_studies(monkeypatch) -> None:
    """A candidate with zero accepted objects must not erase its object attempts."""
    from dataset_generator_m1 import generator as generator_module
    from dataset_generator_m1.config import load_profile
    from dataset_generator_m1.scene import SceneRejected

    diagnostic = build_rejection_record(
        slot=0,
        candidate_attempt=0,
        object_attempt=0,
        asset="assets/landing.png",
        class_name="landing",
        group="default",
        scale=0.2,
        rotation_degrees=0.0,
        estimated_size=(20.0, 20.0),
        requested_objects=1,
        stage="renderer.visibility",
        reason="outside_frame",
    )

    class Planner:
        def __init__(self, *_args):
            pass

        def plan(self, *_args):
            return SimpleNamespace(recipe_id="direct", canvas_size=(1, 1))

    class Synthesizer:
        def __init__(self, *_args):
            pass

        def synthesize(self, *_args):
            return object()

    class Renderer:
        def __init__(self, *_args):
            pass

        def render(self, *_args):
            raise SceneRejected("candidate has no accepted foreground annotations", [diagnostic])

    monkeypatch.setattr(generator_module, "ScenePlanner", Planner)
    monkeypatch.setattr(generator_module, "BackgroundSynthesizer", Synthesizer)
    monkeypatch.setattr(generator_module, "SceneRenderer", Renderer)
    resolved = load_profile("examples/configs/landing_minimal.yaml")

    result = generator_module._produce_slot(resolved, object(), 0, 0, 1)

    assert result["accepted"] is False
    assert result["rejections"][0]["object_rejections"] == [diagnostic]


def test_study_summary_counts_embedded_candidate_object_diagnostics() -> None:
    from dataset_generator_m1.placement_study import collect_study_diagnostics

    diagnostic = build_rejection_record(
        slot=0,
        candidate_attempt=0,
        object_attempt=0,
        asset="assets/landing.png",
        class_name="landing",
        group="default",
        scale=0.2,
        rotation_degrees=0.0,
        estimated_size=(20.0, 20.0),
        requested_objects=1,
        stage="renderer.visibility",
        reason="outside_frame",
    )
    candidate = {"slot": 0, "candidate_attempt": 0, "reason": "SceneRejected", "object_rejections": [diagnostic]}

    evidence = collect_study_diagnostics([], [candidate], Path("unused"))

    assert evidence["candidate_failures"] == [candidate]
    assert evidence["object_rejections"] == [diagnostic]
    assert evidence["diagnostics"]["total_rejections"] == 1


def test_placement_study_uses_a_production_pool_and_writes_linked_report(tmp_path: Path) -> None:
    from dataset_generator_m1.placement_study import (
        PlacementStudyRequest,
        run_placement_study,
        validate_placement_study,
    )

    config = write_derived_composer(
        tmp_path,
        "landing",
        {
            "run": {"label": "placement-test", "num_images": 1, "max_candidate_attempts": 8},
            "output": {"image_size": [96, 96], "image_format": "png"},
            "sampling": {"instances_per_image": [2, 2], "foreground_size": [0.2, 0.2]},
            "scene": {"canvas_scale": 1.25},
            "background_mixing": {"recipe_weights": {"direct": 1.0}},
        },
    )
    output = tmp_path / "placement-study"

    result = run_placement_study(PlacementStudyRequest(config, output, samples=1, qa_samples=1))

    assert result["status"] == "complete"
    assert (output / "study.json").exists()
    assert (output / "rejections.jsonl").exists()
    assert (output / "summary.json").exists()
    assert (output / "report" / "index.html").exists()
    assert (output / "report" / "contact-sheet.jpg").exists()
    html = (output / "report" / "index.html").read_text(encoding="utf-8")
    assert "contact-sheet.jpg" in html
    assert "Placement rejection study" in html
    assert validate_placement_study(output)["status"] == "valid"
