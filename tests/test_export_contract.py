import json
from pathlib import Path

from PIL import Image

from dataset_generator_m1.exporter import ExportOptions, export_pools


def make_pool(root: Path, class_name: str, *, background: str) -> None:
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (8, 8), "gray").save(root / "images" / "same.png")
    (root / "run.json").write_text(json.dumps({"family": {"classes": [class_name]}}), encoding="utf-8")
    sample = {
        "sample_id": "duplicate-id",
        "image_path": "images/same.png",
        "background": {"sources": [background]},
        "annotations": [
            {
                "class_name": class_name,
                "source_asset": "root0/shared-foreground.png",
                "normalized_bbox": [0.5, 0.5, 0.25, 0.25],
            }
        ],
    }
    (root / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")


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
