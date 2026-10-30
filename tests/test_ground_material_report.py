import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image


SCRIPT = Path(__file__).parents[1] / "scripts" / "report_ground_materials.py"
spec = importlib.util.spec_from_file_location("ground_material_report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_report_uses_renderer_schema_and_rejects_unmatched_pairs(tmp_path):
    ids = ("span-1", "span-fallback", "span-0-5", "span-1-5", "span-1-5-missing")
    matrix = {"purpose": "synthetic", "cells": [
        {"id": "span-1", "ground_indices": [0, 1], "ground_mapping": {"ground_spans": [1, 1]}, "treatment": {}, "environment": "open"},
        {"id": "span-fallback", "ground_indices": [0, 1], "treatment": {}, "environment": "open"},
        {"id": "span-0-5", "ground_indices": [0, 1], "ground_mapping": {"ground_spans": [.5, .5]}, "treatment": {}, "environment": "open"},
        {"id": "span-1-5", "ground_indices": [0, 1], "ground_mapping": {"ground_spans": [1.5, 1.5]}, "treatment": {}, "environment": "open"},
        {"id": "span-1-5-missing", "ground_indices": [0, 1], "ground_mapping": {"ground_spans": [1.5, 1.5]}, "treatment": {}, "environment": "open"},
    ]}
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix))
    root = tmp_path / "extracted" / "results"
    mask = np.zeros((1, 16, 16), dtype=np.uint8)
    mask[:, 5:10, 5:10] = 1
    records = []
    for idx, cid in enumerate(ids[:-1]):
        job = "000-base-fast"
        folder = root / cid / "scenes" / job
        folder.mkdir(parents=True)
        rgb = np.full((16, 16, 3), idx * 10, dtype=np.uint8)
        Image.fromarray(rgb).save(folder / "rgb.png")
        cell_mask = mask.copy()
        if cid == "span-1-5":
            cell_mask[:, 1:3, 1:3] = 1  # Actual mismatch despite identical declared record signatures.
        np.savez(folder / "masks.npz", visible=cell_mask, full=cell_mask.copy())
        scene = {"objects": [{"source_sha256": "artwork-a", "placement": [1, 2, 3]}]}
        ref_index = 4
        if cid == "span-0-5":
            ref_index = 7  # Same camera, different reference scene.
        result = {
            "status": "accepted",
            "job": {"reference_scene_index": ref_index, "scene": scene,
                    "ground_index": 0,
                    "treatment": {"ground_material": {"mode": "coherent-blend", "primary_index": None, "donor_index": 1}}},
            "renderer_settings": {"camera_to_world_opengl": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], "output_resolution": [16, 16]},
            "intrinsics_K_before_distortion": [[10, 0, 8], [0, 10, 8], [0, 0, 1]],
            "surface_diagnostics": {"ground_index": 0},
            "ground_diagnostics": {"achieved_spans": 1},
            "environment_geometry_diagnostics": {"environment": "open"},
        }
        (folder / "result.json").write_text(json.dumps(result))
        # These are the true fields written by the driver: cell object, job, string identity, diagnostics and outcome.
        records.append({"cell": matrix["cells"][idx], "job": job, "identity": "study-contract-sha256",
                        "outcome": {"command_seconds": 2.5, "sampled_peak_gpu_memory_mib": 120},
                        "ground_diagnostics": result["ground_diagnostics"],
                        "environment_diagnostics": result["environment_geometry_diagnostics"],
                        "mask_signature": {"visible": "same-declared-signature"}})
        study = {"grounds": [{"provenance": {"asset_id": "granite-primary"}},
                              {"provenance": {"asset_id": "sand-donor"}}]}
        (root / cid / "study.json").write_text(json.dumps(study))
    root.mkdir(parents=True, exist_ok=True)
    (root / "summary.json").write_text(json.dumps({"status": "partial", "records": records}))
    html_path = tmp_path / "report.html"
    payload = report.build(root, matrix_path, html_path)

    metrics = {row["cell"]: row for row in payload["metrics"]}
    assert metrics["span-fallback"]["paired"] is True
    assert metrics["span-fallback"]["comparison_baseline"] == "span-1"
    assert metrics["span-fallback"]["rgb_mae"] == 10
    assert metrics["span-fallback"]["ground_assets"] == ["granite-primary", "sand-donor"]
    assert metrics["span-0-5"]["paired"] is False
    assert "rgb_mae" not in metrics["span-0-5"]
    assert metrics["span-1-5"]["mask_mismatch"] is True
    assert "rgb_mae" not in metrics["span-1-5"]
    assert metrics["span-1-5-missing"]["status"] == "missing"
    assert metrics["span-1"]["comparison_role"] == "baseline"
    assert "MASK MISMATCH" in html_path.read_text()
    assert html_path.with_suffix(".metrics.json").is_file()
