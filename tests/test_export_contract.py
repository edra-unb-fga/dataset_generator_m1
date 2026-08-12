import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dataset_generator_m1.annotation_evidence import encode_mask_evidence
from dataset_generator_m1.exporter import ExportOptions, export_pools


def make_pool(root: Path, class_name: str, *, background: str, schema_version: int = 1) -> None:
    (root / "images").mkdir(parents=True)
    (root / "qa").mkdir()
    Image.new("RGB", (8, 8), "gray").save(root / "images" / "same.png")
    run = {
        "schema_version": schema_version,
        "run_id": f"run-{class_name}",
        "contract_hash": f"contract-{class_name}",
        "catalog_fingerprint": f"catalog-{class_name}",
        "family": {"classes": [class_name]},
        "profile": {"run": {"num_images": 1}, "output": {"image_size": [8, 8]}},
    }
    if schema_version == 2:
        run["capabilities"] = {"detection_boxes": True, "full_instance_coverage": True, "visible_instance_coverage": True}
        run["annotation_policy"] = {"alpha_threshold": 8, "default_mask_semantics": "visible"}
    (root / "run.json").write_text(json.dumps(run), encoding="utf-8")
    sample = {
        "sample_id": "duplicate-id",
        "image_path": "images/same.png",
        "background": {"sources": [background]},
        "annotations": [
            {
                "class_name": class_name,
                "source_asset": "root0/shared-foreground.png",
                "bbox": [2, 2, 6, 6],
                "normalized_bbox": [0.5, 0.5, 0.5, 0.5],
            }
        ],
    }
    if schema_version == 2:
        sample["annotations"][0]["instance_id"] = "instance-000"
        mask = np.zeros((8, 8), dtype=np.uint8)
        mask[2:6, 2:6] = 255
        encoded = encode_mask_evidence((mask,), (mask,), ("instance-000",), image_size=(8, 8), alpha_threshold=8)
        (root / "masks").mkdir()
        (root / "masks" / "same.npz").write_bytes(encoded.archive_bytes)
        sample["mask_evidence"] = {**encoded.manifest, "path": "masks/same.npz"}
    (root / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    (root / "summary.json").write_text(json.dumps({"status": "complete", "accepted_samples": 1, "contract_hash": run["contract_hash"]}), encoding="utf-8")
    (root / "control.json").write_text(json.dumps({"actual_state": "complete"}), encoding="utf-8")
    for name in ("rejections.jsonl", "metrics.jsonl", "control-events.jsonl"):
        (root / name).write_text("", encoding="utf-8")
    (root / "qa" / "index.html").write_text("<html></html>", encoding="utf-8")


def test_export_handles_pool_identity_collisions_and_remaps_classes(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    make_pool(left, "class-a", background="root0/a.png")
    make_pool(right, "class-b", background="root0/b.png")

    summary = export_pools(
        [left, right],
        tmp_path / "export",
        ExportOptions(strategy="asset-disjoint", splits={"train": 0.5, "val": 0.5}, preserve_names=True),
    )

    assert len(summary["samples"]) == 2
    assert len({sample["filename"] for sample in summary["samples"]}) == 2
    assert len({sample["split"] for sample in summary["samples"]}) == 1
    assert summary["classes"] == ["class-a", "class-b"]
    labels = sorted((tmp_path / "export" / "labels").rglob("*.txt"))
    assert {label.read_text(encoding="utf-8").split()[0] for label in labels} == {"0", "1"}
    serialized = (tmp_path / "export" / "export.json").read_text(encoding="utf-8")
    assert str(left.resolve()) not in serialized and str(right.resolve()) not in serialized


@pytest.mark.parametrize("strategy", ["random", "stratified", "asset-disjoint"])
def test_segmentation_export_uses_mask_evidence_and_records_fidelity(tmp_path: Path, strategy: str) -> None:
    pool = tmp_path / "pool"
    make_pool(pool, "class-a", background="root0/a.png", schema_version=2)

    summary = export_pools(
        [pool],
        tmp_path / "segmentation",
        ExportOptions(task="segmentation", mask_semantics="family", strategy=strategy, splits={"train": 1.0}),
    )

    label = next((tmp_path / "segmentation" / "labels").rglob("*.txt")).read_text(encoding="utf-8").split()
    assert label[0] == "0"
    assert len(label) >= 7
    assert summary["task"] == "segmentation"
    assert summary["mask_semantics"] == "visible"
    assert summary["status"] == "complete"
    assert summary["fidelity"]["instances"] == 1
    assert summary["source_pools"][0]["run_id"] == "run-class-a"


def test_segmentation_export_rejects_v1_before_creating_output(tmp_path: Path) -> None:
    pool = tmp_path / "pool"
    output = tmp_path / "segmentation"
    make_pool(pool, "class-a", background="root0/a.png", schema_version=1)

    with pytest.raises(ValueError, match="pool schema v2"):
        export_pools([pool], output, ExportOptions(task="segmentation"))
    assert not output.exists()


def test_full_and_visible_segmentation_semantics_are_independently_exportable(tmp_path: Path) -> None:
    pool = tmp_path / "pool"
    make_pool(pool, "class-a", background="root0/a.png", schema_version=2)
    full = np.zeros((8, 8), dtype=np.uint8)
    visible = np.zeros_like(full)
    full[1:7, 1:7] = 255
    visible[2:6, 2:6] = 255
    encoded = encode_mask_evidence((full,), (visible,), ("instance-000",), image_size=(8, 8), alpha_threshold=8)
    (pool / "masks" / "same.npz").write_bytes(encoded.archive_bytes)
    sample = json.loads((pool / "samples.jsonl").read_text(encoding="utf-8"))
    sample["mask_evidence"] = {**encoded.manifest, "path": "masks/same.npz"}
    (pool / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")

    visible_summary = export_pools(
        [pool], tmp_path / "visible", ExportOptions(task="segmentation", mask_semantics="visible", splits={"train": 1.0})
    )
    full_summary = export_pools(
        [pool], tmp_path / "full", ExportOptions(task="segmentation", mask_semantics="full", splits={"train": 1.0})
    )

    visible_label = next((tmp_path / "visible" / "labels").rglob("*.txt")).read_text(encoding="utf-8")
    full_label = next((tmp_path / "full" / "labels").rglob("*.txt")).read_text(encoding="utf-8")
    assert visible_label != full_label
    assert visible_summary["mask_semantics"] == "visible"
    assert full_summary["mask_semantics"] == "full"


def test_lossy_topology_completes_export_with_actionable_warnings(tmp_path: Path) -> None:
    pool = tmp_path / "pool"
    make_pool(pool, "class-a", background="root0/a.png", schema_version=2)
    mask = np.zeros((8, 8), dtype=np.uint8)
    mask[1:7, 1:7] = 255
    mask[3:5, 3:5] = 0
    encoded = encode_mask_evidence((mask,), (mask,), ("instance-000",), image_size=(8, 8), alpha_threshold=8)
    (pool / "masks" / "same.npz").write_bytes(encoded.archive_bytes)
    sample = json.loads((pool / "samples.jsonl").read_text(encoding="utf-8"))
    sample["annotations"][0]["bbox"] = [1, 1, 7, 7]
    sample["annotations"][0]["normalized_bbox"] = [0.5, 0.5, 0.75, 0.75]
    sample["mask_evidence"] = {**encoded.manifest, "path": "masks/same.npz"}
    (pool / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")

    summary = export_pools(
        [pool], tmp_path / "segmentation", ExportOptions(task="segmentation", splits={"train": 1.0})
    )

    assert summary["status"] == "complete_with_warnings"
    assert summary["fidelity"]["warning_instances"] == 1
    codes = {item["code"] for item in summary["fidelity"]["findings"][0]["warnings"]}
    assert "MASK_HOLES_FILLED" in codes
