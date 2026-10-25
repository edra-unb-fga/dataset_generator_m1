"""Exercise offline analysis with explicitly fabricated perfect predictions, never a model claim."""
import argparse
import json
from pathlib import Path

from dataset_generator_m1.analysis_reports import fresh_output, write_report
from dataset_generator_m1.evaluation_io import prepare_dataset
from dataset_generator_m1.evaluation import score_dataset, compare_scores
from dataset_generator_m1.reference_analysis import audit_references, check_projection


def run(pool, output_dir):
    root = fresh_output(output_dir)
    manifest = root / "input.json"
    manifest.write_text(json.dumps({"schema_version": 1, "format": "pool", "source": str(Path(pool).resolve()),
                                    "domain": "synthetic", "role": "regression", "annotation_semantics": "visible"}))
    dataset = prepare_dataset(manifest, root / "dataset")
    ground_truth = dataset["ground_truth"]
    predictions = [{**{k: a[k] for k in ("image_id", "category_id", "bbox", "segmentation")}, "score": .99}
                   for a in ground_truth["annotations"]]
    (root / "oracle.json").write_text(json.dumps(predictions))
    prediction_manifest = root / "predictions.json"
    prediction_manifest.write_text(json.dumps({"schema_version": 1, "dataset_sha256": dataset["dataset_sha256"],
                                               "image_ids": [r["id"] for r in ground_truth["images"]], "predictions": "oracle.json",
                                               "model": {"id": "fabricated-perfect-predictions; not trained or inferred"}}))
    result = score_dataset(root / "dataset", prediction_manifest, root / "score")
    for task in ("bbox", "segm"):
        if ground_truth["annotations"]:
            assert abs(result["tasks"][task]["metrics"]["AP"]-1) < 1e-9
    compare_scores(root / "score", root / "score", root / "comparison")
    references = {"schema_version": 1, "domain": "synthetic", "role": "regression", "image_root": "dataset", "images": [
        {"id": str(image["id"]), "path": image["file_name"], "conditions": {"origin": "synthetic pool"},
         "annotations": [{"bbox": a["bbox"], "class_name": next(c["name"] for c in ground_truth["categories"] if c["id"] == a["category_id"])}
                         for a in ground_truth["annotations"] if a["image_id"] == image["id"]]}
        for image in ground_truth["images"][:16]]}
    (root / "reference.json").write_text(json.dumps(references))
    audit_references(root / "reference.json", root / "audit")
    check_projection(Path(__file__).resolve().parents[1] / "examples/reference/projection.json", root / "projection")
    return write_report(root, {"schema_version": 1, "status": "complete_with_warnings", "kind": "analysis-smoke",
                               "score_tasks": result["tasks"], "reports": ["dataset/index.html", "score/index.html", "comparison/index.html", "audit/index.html", "projection/index.html"],
                               "warnings": ["All predictions were fabricated from ground truth to verify plumbing. No detector was run or evaluated on real images."]},
                        "Offline analysis correctness smoke")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run(args.pool, args.output_dir)
