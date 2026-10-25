import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

pytest.importorskip("pycocotools")

from dataset_generator_m1.evaluation import score_dataset, compare_scores
from dataset_generator_m1.evaluation_io import prepare_dataset, encode_mask, instance_mask, validate_coco
from dataset_generator_m1.inspection import _LocalLinks


def fixture_dataset(tmp_path, *, crowd=False):
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (64, 64), "#668844").save(source / "first.png")
    Image.new("RGB", (64, 64), "#777766").save(source / "negative.png")
    mask = np.zeros((64, 64), np.uint8)
    mask[10:30, 10:30] = 1
    mask[15:20, 15:20] = 0
    annotation = {"id": 1, "image_id": 1, "category_id": 0, "bbox": [10, 10, 20, 20],
                  "segmentation": encode_mask(mask), "iscrowd": int(crowd)}
    ground_truth = {"images": [{"id": 1, "file_name": "first.png", "width": 64, "height": 64},
                               {"id": 2, "file_name": "negative.png", "width": 64, "height": 64}],
                    "categories": [{"id": 0, "name": "pad"}, {"id": 1, "name": "unused"}], "annotations": [annotation]}
    (source / "gt.json").write_text(json.dumps(ground_truth))
    manifest = {"schema_version": 1, "format": "coco", "domain": "synthetic", "role": "regression",
                "source": "source", "ground_truth": "gt.json", "annotation_semantics": "visible"}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    result = prepare_dataset(path, tmp_path / "prepared")
    prediction = {k: v for k, v in annotation.items() if k not in {"id", "iscrowd"}}
    prediction["score"] = .9
    return result, prediction


def score(tmp_path, dataset, predictions, name="score", **changes):
    (tmp_path / f"{name}-predictions.json").write_text(json.dumps(predictions))
    manifest = {"schema_version": 1, "dataset_sha256": dataset["dataset_sha256"], "image_ids": [1, 2],
                "predictions": f"{name}-predictions.json", **changes}
    path = tmp_path / f"{name}-manifest.json"
    path.write_text(json.dumps(manifest))
    return score_dataset(tmp_path / "prepared", path, tmp_path / name)


def test_perfect_boxes_and_exact_holey_masks_and_report_links(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    result = score(tmp_path, dataset, [prediction])
    for task in ("bbox", "segm"):
        assert result["tasks"][task]["metrics"]["AP"] == pytest.approx(1)
        assert result["tasks"][task]["per_class"][1]["AP"] is None
        assert result["tasks"][task]["operating_point"]["tp"] == 1
    links = _LocalLinks()
    links.feed((tmp_path / "score/index.html").read_text())
    assert links.values and all((tmp_path / "score" / p).is_file() for p in links.values)


def test_duplicate_and_negative_predictions_are_false_positives(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    result = score(tmp_path, dataset, [prediction, dict(prediction, score=.8), dict(prediction, image_id=2)])
    for task in ("bbox", "segm"):
        point = result["tasks"][task]["operating_point"]
        assert (point["tp"], point["fp"], point["fn"]) == (1, 2, 0)
        assert point["precision"] == pytest.approx(1/3)


def test_empty_and_wrong_class_predictions(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    empty = score(tmp_path, dataset, [], "empty")
    wrong = score(tmp_path, dataset, [dict(prediction, category_id=1)], "wrong")
    assert empty["tasks"]["segm"]["metrics"]["AP"] == 0
    assert empty["tasks"]["bbox"]["operating_point"]["fn"] == 1
    assert wrong["tasks"]["bbox"]["operating_point"]["fp"] == 1


def test_crowd_predictions_are_ignored_and_unsupported_ap_unavailable(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path, crowd=True)
    result = score(tmp_path, dataset, [prediction, dict(prediction, score=.8)])
    for task in ("bbox", "segm"):
        assert result["tasks"][task]["metrics"]["AP"] is None
        assert result["tasks"][task]["operating_point"]["ignored_predictions"] == 2
        assert result["tasks"][task]["operating_point"]["fp"] == 0


@pytest.mark.parametrize("change", [{"image_id": 99}, {"category_id": 99}, {"score": float("nan")},
                                    {"bbox": [-1, 0, 5, 5]}, {"segmentation": {"size": [32, 32], "counts": "bad"}}])
def test_bad_predictions_fail_before_output(tmp_path, change):
    dataset, prediction = fixture_dataset(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        score(tmp_path, dataset, [dict(prediction, **change)])
    assert not (tmp_path / "score").exists()


def test_coverage_and_comparison_identity(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    with pytest.raises(ValueError, match="coverage"):
        score(tmp_path, dataset, [prediction], "omitted", image_ids=[1])
    score(tmp_path, dataset, [prediction], "a")
    score(tmp_path, dataset, [prediction], "b")
    result = compare_scores(tmp_path / "a", tmp_path / "b", tmp_path / "comparison")
    assert result["metric_deltas_right_minus_left"]["segm"]["AP"] == 0
    score(tmp_path, dataset, [prediction], "partial", image_ids=[1], allow_partial=True)
    with pytest.raises(ValueError, match="incompatible"):
        compare_scores(tmp_path / "a", tmp_path / "partial", tmp_path / "invalid-comparison")


def test_prediction_record_order_does_not_change_metrics(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    predictions = [prediction, dict(prediction, score=.7), dict(prediction, image_id=2, score=.5)]
    a = score(tmp_path, dataset, predictions, "a")
    b = score(tmp_path, dataset, list(reversed(predictions)), "b")
    assert a["tasks"] == b["tasks"]


def test_prepared_image_tampering_is_rejected(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    Image.new("RGB", (64, 64), "white").save(tmp_path / "prepared/images/1.png")
    with pytest.raises(ValueError, match="hash"):
        score(tmp_path, dataset, [prediction])


def test_pool_and_bound_export_adapters_preserve_exact_truth(tmp_path):
    from helpers import write_derived_composer
    from dataset_generator_m1.config import load_profile
    from dataset_generator_m1.generator import generate_pool, GenerationOptions
    from dataset_generator_m1.exporter import export_pools, ExportOptions
    config = write_derived_composer(tmp_path, "landing-pad", {
        "run": {"num_images": 1}, "output": {"image_size": [96, 96]},
        "background_mixing": {"recipe_weights": {"direct": 1.0}}, "reporting": {"qa_samples": 0}})
    assert generate_pool(load_profile(config), tmp_path / "pool", GenerationOptions(display="quiet"))["status"] == "complete"
    export_pools([tmp_path / "pool"], tmp_path / "export", ExportOptions(task="segmentation", splits={"test": 1.0}))
    manifest = {"schema_version": 1, "format": "yolo-export", "source": "export", "domain": "synthetic", "role": "regression",
                "annotation_semantics": "visible", "split": "test", "pool_bindings": {"pool-000": "pool"}}
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps(manifest))
    result = prepare_dataset(path, tmp_path / "prepared")
    assert result["provenance"]["mask_reference"] == "exact-pool"
    assert result["provenance"]["export_fidelity"]["instances"] > 0
    assert result["metadata"]["1"]["recipe_id"] == "direct"
    assert result["metadata"]["1"]["effect_traces"]
    unbound = dict(manifest, pool_bindings={}, annotation_semantics="full")
    path.write_text(json.dumps(unbound))
    with pytest.raises(ValueError, match="semantics"):
        prepare_dataset(path, tmp_path / "wrong-semantics")
    path.write_text(json.dumps(manifest))
    run = tmp_path / "pool/run.json"
    run.write_text(run.read_text()+" ")
    with pytest.raises(ValueError, match="hash"):
        prepare_dataset(path, tmp_path / "bad")


@pytest.mark.parametrize("counts", ["0", "1", "P", "!!!!", ""])
def test_truncated_compressed_masks_fail_before_native_decode(counts):
    with pytest.raises(ValueError, match="RLE"):
        instance_mask({"size": [4, 4], "counts": counts}, 4, 4)


def test_annotation_zero_is_rejected_before_backend_matching(tmp_path):
    dataset, _ = fixture_dataset(tmp_path)
    coco = dataset["ground_truth"]
    coco["annotations"][0]["id"] = 0
    with pytest.raises(ValueError, match="positive"):
        validate_coco(coco)


@pytest.mark.parametrize("format", ["pool", "yolo-export"])
def test_synthetic_sources_cannot_be_declared_real(tmp_path, format):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "format": format, "domain": "real", "role": "held-out", "annotation_semantics": "visible"}))
    with pytest.raises(ValueError, match="synthetic"):
        prepare_dataset(path, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_prediction_content_has_identity_independent_of_manifest(tmp_path):
    dataset, prediction = fixture_dataset(tmp_path)
    a = score(tmp_path, dataset, [prediction], "a")
    b = score(tmp_path, dataset, [], "b")
    assert a["prediction_file_sha256"] != b["prediction_file_sha256"]
    assert a["normalized_predictions_sha256"] != b["normalized_predictions_sha256"]
