"""Canonical offline box/mask scoring and compatible experiment comparisons."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from importlib.metadata import version
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .analysis_reports import digest, file_hash, fresh_output, local_artifact, read_json, write_report
from .evaluation_io import instance_mask, mask_backend, valid_box, validate_coco
from .analysis_contracts import PredictionManifest


def _dataset(path):
    path = Path(path).resolve()
    path = path / "dataset.json" if path.is_dir() else path
    data = read_json(path)
    if data.get("schema_version") != 1 or data.get("kind") != "evaluation-dataset":
        raise ValueError("Expected a prepared evaluation dataset")
    expected = digest({k: v for k, v in data.items() if k not in {"status", "warnings", "dataset_sha256"}})
    if data.get("dataset_sha256") != expected:
        raise ValueError("Prepared dataset identity does not match its contents")
    validate_coco(data["ground_truth"])
    for image in data["ground_truth"]["images"]:
        if file_hash(local_artifact(path.parent, image["file_name"])) != image["sha256"]:
            raise ValueError("Prepared image hash changed")
    return data, path.parent


def _predictions(path, dataset, tasks):
    path = Path(path).resolve()
    manifest = PredictionManifest.model_validate(read_json(path)).model_dump(exclude_none=True)
    if manifest.get("schema_version") != 1 or manifest.get("dataset_sha256") != dataset["dataset_sha256"]:
        raise ValueError("Prediction manifest must bind the prepared dataset identity")
    images = {r["id"]: r for r in dataset["ground_truth"]["images"]}
    ids = manifest.get("image_ids")
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in images for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Explicit unique processed image_ids are required, including images with no detections")
    if set(ids) != set(images) and manifest.get("allow_partial") is not True:
        raise ValueError("Omitted prediction coverage requires explicit allow_partial")
    predictions = read_json(path.parent / manifest["predictions"])
    if not isinstance(predictions, list):
        raise ValueError("COCO predictions must be a JSON list")
    classes = {r["id"] for r in dataset["ground_truth"]["categories"]}
    normalized = []
    for row in predictions:
        if not isinstance(row, dict) or type(row.get("image_id")) is not int or type(row.get("category_id")) is not int or row["image_id"] not in ids or row.get("category_id") not in classes:
            raise ValueError("Prediction references an unknown or unprocessed image/class")
        score = row.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not np.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Prediction confidence must be finite and in [0,1]")
        image = images[row["image_id"]]
        item = {"image_id": row["image_id"], "category_id": row["category_id"], "score": float(score)}
        if "bbox" in tasks:
            item["bbox"] = valid_box(row.get("bbox"), image["width"], image["height"])
        if "segm" in tasks:
            from .evaluation_io import encode_mask
            item["segmentation"] = encode_mask(instance_mask(row.get("segmentation"), image["width"], image["height"]))
        normalized.append(item)
    normalized.sort(key=lambda r: (-r["score"], r["image_id"], r["category_id"], digest(r)))
    return normalized, sorted(ids), manifest


def _coco_objects(ground_truth, predictions, task):
    mask_backend()  # Give the optional-extra diagnostic before importing the backend.
    from pycocotools.coco import COCO
    gt = COCO()
    gt.dataset = deepcopy(ground_truth)
    gt.createIndex()
    rows = [{k: v for k, v in r.items() if k != ("bbox" if task == "segm" else "segmentation")} for r in predictions]
    if rows:
        dt = gt.loadRes(rows)
    else:  # COCO.loadRes([]) indexes the first result; empty predictions are valid.
        dt = COCO()
        dt.dataset = {"images": deepcopy(gt.dataset["images"]), "categories": deepcopy(gt.dataset["categories"]), "annotations": []}
        dt.createIndex()
    return gt, dt


def _metrics(ground_truth, predictions, ids, task, confidence, diagnostic_iou):
    mask_backend()
    from pycocotools.cocoeval import COCOeval
    gt, dt = _coco_objects(ground_truth, predictions, task)
    evaluator = COCOeval(gt, dt, task)
    evaluator.params.imgIds = ids
    evaluator.evaluate()
    evaluator.accumulate()
    evaluator.summarize()
    names = ("AP", "AP50", "AP75", "AP_small", "AP_medium", "AP_large", "AR1", "AR10", "AR100", "AR_small", "AR_medium", "AR_large")
    metrics = {name: float(v) if v >= 0 else None for name, v in zip(names, evaluator.stats)}
    per_class = []
    for index, category in enumerate(sorted(ground_truth["categories"], key=lambda r: r["id"])):
        values = evaluator.eval["precision"][:, :, index, 0, -1]
        values = values[values >= 0]
        per_class.append({"id": category["id"], "name": category["name"], "AP": float(values.mean()) if values.size else None,
                          "ground_truth_instances": sum(a["category_id"] == category["id"] and a["image_id"] in ids and not a.get("iscrowd", 0) for a in ground_truth["annotations"])})
    # Diagnostics use the canonical matcher's crowd/ignore semantics at one declared operating point.
    filtered = [p for p in predictions if p["score"] >= confidence]
    dg, dd = _coco_objects(ground_truth, filtered, task)
    diagnostic = COCOeval(dg, dd, task)
    diagnostic.params.imgIds = ids
    diagnostic.params.iouThrs = np.array([diagnostic_iou])
    diagnostic.params.areaRng = [[0, 1e10]]
    diagnostic.params.areaRngLbl = ["all"]
    diagnostic.evaluate()
    rows = {i: {"image_id": i, "tp": 0, "fp": 0, "fn": 0, "ignored_predictions": 0, "false_positive_ids": [], "false_negative_ids": []} for i in ids}
    for item in diagnostic.evalImgs:
        if item is None:
            continue
        row = rows[item["image_id"]]
        for dt_id, match, ignore in zip(item["dtIds"], item["dtMatches"][0], item["dtIgnore"][0]):
            if ignore:
                row["ignored_predictions"] += 1
            elif match:
                row["tp"] += 1
            else:
                row["fp"] += 1
                row["false_positive_ids"].append(int(dt_id))
        for gt_id, match, ignore in zip(item["gtIds"], item["gtMatches"][0], item["gtIgnore"]):
            if not ignore and not match:
                row["fn"] += 1
                row["false_negative_ids"].append(int(gt_id))
    counts = {k: sum(r[k] for r in rows.values()) for k in ("tp", "fp", "fn", "ignored_predictions")}
    counts["precision"] = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else None
    counts["recall"] = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else None
    return {"metrics": metrics, "per_class": per_class, "operating_point": {"confidence": confidence, "iou": diagnostic_iou, "max_detections_per_image_per_class": 100, **counts},
            "per_image": list(rows.values())}, dd


def _overlays(output, root, ground_truth, diagnostics, detections, task):
    cards = []
    output.joinpath("overlays").mkdir(exist_ok=True)
    images = {r["id"]: r for r in ground_truth["images"]}
    ordered = sorted(diagnostics, key=lambda r: (-(r["fp"] + r["fn"]), r["image_id"]))[:16]
    for row in ordered:
        image = images[row["image_id"]]
        with Image.open(local_artifact(root, image["file_name"])) as source:
            canvas = source.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        for a in ground_truth["annotations"]:
            if a["image_id"] == row["image_id"]:
                x, y, w, h = a["bbox"]
                draw.rectangle((x, y, x+w, y+h), outline="#00bd8e", width=2)
        for prediction_id in row["false_positive_ids"]:
            a = detections.anns[prediction_id]
            x, y, w, h = a["bbox"]
            draw.rectangle((x, y, x+w, y+h), outline="#f14057", width=2)
        if task == "segm":
            tint = np.asarray(canvas).copy()
            for a in ground_truth["annotations"]:
                if a["image_id"] == row["image_id"]:
                    mask = instance_mask(a["segmentation"], image["width"], image["height"])
                    tint[mask] = (tint[mask].astype(float)*.7 + np.array([0, 190, 130])*.3).astype(np.uint8)
            for prediction_id in row["false_positive_ids"]:
                a = detections.anns[prediction_id]
                mask = instance_mask(a["segmentation"], image["width"], image["height"])
                tint[mask] = (tint[mask].astype(float)*.7 + np.array([241, 64, 87])*.3).astype(np.uint8)
            canvas = Image.fromarray(tint)
        targets = [a for a in ground_truth["annotations"] if a["image_id"] == row["image_id"]]
        targets.sort(key=lambda a: (a["id"] not in row["false_negative_ids"], a["id"]))
        for index, a in enumerate(targets[:2]):
            x, y, w, h = a["bbox"]
            margin = max(4, round(max(w, h)*.15))
            crop = canvas.crop((max(0, int(x)-margin), max(0, int(y)-margin), min(image["width"], int(np.ceil(x+w))+margin), min(image["height"], int(np.ceil(y+h))+margin)))
            crop.thumbnail((480, 480))
            name = f"overlays/{task}-{row['image_id']}-target-{index}.jpg"
            crop.save(output / name, quality=90)
            cards.append((name, f"{task} target {a['id']} | {'missed at operating point' if a['id'] in row['false_negative_ids'] else 'reference crop'}"))
        canvas.thumbnail((960, 960))
        path = f"overlays/{task}-{row['image_id']}.jpg"
        canvas.save(output / path, quality=90)
        cards.append((path, f"{task} image {row['image_id']}: TP {row['tp']}, FP {row['fp']}, FN {row['fn']}; green ground truth, red false positives"))
    return cards


def score_dataset(dataset_path, predictions_manifest, output_dir, *, tasks=("bbox", "segm"), confidence=.25, diagnostic_iou=.5):
    if not tasks or set(tasks) - {"bbox", "segm"} or len(set(tasks)) != len(tasks):
        raise ValueError("Tasks must be unique bbox and/or segm")
    if not 0 <= confidence <= 1 or not 0 < diagnostic_iou <= 1:
        raise ValueError("Invalid diagnostic confidence or IoU")
    dataset, root = _dataset(dataset_path)
    predictions, ids, manifest = _predictions(predictions_manifest, dataset, tasks)
    ground_truth = dataset["ground_truth"]
    if "segm" in tasks and any("segmentation" not in a for a in ground_truth["annotations"]):
        raise ValueError("Segmentation scoring requires masks for every ground-truth instance")
    output = fresh_output(output_dir)
    results, cards = {}, []
    for task in tasks:
        with redirect_stdout(io.StringIO()):
            results[task], detections = _metrics(ground_truth, predictions, ids, task, confidence, diagnostic_iou)
        cards.extend(_overlays(output, root, ground_truth, results[task]["per_image"], detections, task))
    slices = {}
    # Only image-level attributes supplied by the dataset are used as slice labels.
    for key in ("capture_session", "location", "lighting", "material", "recipe_id", "perspective_status", "clipping_status", "occlusion_status"):
        groups = {}
        for image_id in ids:
            metadata = dataset.get("metadata", {}).get(str(image_id), {})
            value = metadata.get(key, "unknown")
            if key == "perspective_status" and metadata.get("perspective_quad") is not None:
                quad = np.asarray(metadata["perspective_quad"], dtype=float)
                affine = np.allclose(quad[0]+quad[2], quad[1]+quad[3], atol=1e-6)
                value = "sampled-affine" if affine else "sampled-projective; not camera tilt"
            if key in {"clipping_status", "occlusion_status"}:
                fractions = metadata.get("clipping_bbox_fractions" if key == "clipping_status" else "visible_support_fractions", [])
                known = [v for v in fractions if isinstance(v, (int, float))]
                value = ("some-targets-reduced" if min(known) < .999 else "all-targets-full") if known else "unknown"
            groups.setdefault(str(value), []).append(image_id)
        slices[key] = {label: {"images": len(members), "operating_counts": {
            task: {k: sum(r[k] for r in results[task]["per_image"] if r["image_id"] in members) for k in ("tp", "fp", "fn")}
            for task in tasks}} for label, members in groups.items()}
    warnings = list(dataset["warnings"])
    relative_sizes = {}
    images = {r["id"]: r for r in ground_truth["images"]}
    for label, low, high in (("box-area-below-1pct", 0, .01), ("box-area-1-to-10pct", .01, .1), ("box-area-at-least-10pct", .1, float("inf"))):
        selected = []
        for annotation in ground_truth["annotations"]:
            if annotation["image_id"] not in ids or annotation.get("iscrowd", 0):
                continue
            image = images[annotation["image_id"]]
            area = annotation["bbox"][2]*annotation["bbox"][3]/(image["width"]*image["height"])
            if low <= area < high:
                selected.append(annotation["id"])
        relative_sizes[label] = {"ground_truth_instances": len(selected), "misses": {
            task: sum(a in selected for r in results[task]["per_image"] for a in r["false_negative_ids"]) for task in tasks},
            "definition": "measured box area / image area; FP have no ground-truth size bin"}
    if len(ids) != len(ground_truth["images"]):
        warnings.append("Partial prediction coverage: this is not a full-dataset score.")
    if manifest.get("model") is None:
        warnings.append("Model/checkpoint/training provenance is unknown.")
    comparison = {"dataset_sha256": dataset["dataset_sha256"], "image_ids": ids, "domain": dataset["domain"],
                  "role": dataset["role"], "annotation_semantics": dataset["annotation_semantics"],
                  "categories": ground_truth["categories"], "tasks": sorted(tasks),
                  "backend": {"name": "pycocotools", "version": version("pycocotools")},
                  "metric_parameters": {"iou_thresholds": [round(.5+.05*i, 2) for i in range(10)], "max_detections": [1, 10, 100],
                                        "confidence": confidence, "diagnostic_iou": diagnostic_iou}}
    result = {"schema_version": 1, "kind": "evaluation-score", "status": "complete_with_warnings",
              "comparison": comparison, "tasks": results, "slices": slices, "relative_target_size_support": relative_sizes, "warnings": warnings,
              "prediction_manifest_sha256": file_hash(predictions_manifest), "model": manifest.get("model", "unknown"),
              "prediction_file_sha256": file_hash(Path(predictions_manifest).resolve().parent / manifest["predictions"]),
              "normalized_predictions_sha256": digest(predictions),
              "ground_truth_reference": dataset["provenance"]["mask_reference"],
              "export_fidelity": dataset["provenance"].get("export_fidelity"),
              "training_provenance": dataset.get("training_provenance", "unknown")}
    return write_report(output, result, "External prediction evaluation", images=cards)


def compare_scores(left, right, output_dir):
    def load(path):
        path = Path(path)
        data = read_json(path / "summary.json" if path.is_dir() else path)
        if data.get("kind") != "evaluation-score" or data.get("schema_version") != 1:
            raise ValueError("Comparison requires evaluation-score artifacts")
        return data
    a, b = load(left), load(right)
    if a["comparison"] != b["comparison"]:
        raise ValueError("Evaluation dataset, coverage, task, policy or scorer settings are incompatible")
    if a["comparison"]["annotation_semantics"] == "unknown":
        raise ValueError("Unknown annotation semantics cannot establish a comparable policy")
    deltas = {task: {key: (b["tasks"][task]["metrics"][key]-value if value is not None and b["tasks"][task]["metrics"][key] is not None else None)
                     for key, value in a["tasks"][task]["metrics"].items()} for task in a["tasks"]}
    output = fresh_output(output_dir)
    return write_report(output, {"schema_version": 1, "status": "complete_with_warnings", "kind": "evaluation-comparison",
                                "comparison": a["comparison"], "metric_deltas_right_minus_left": deltas,
                                "models": [a["model"], b["model"]],
                                "warnings": ["Repeated training seeds and capture-cluster uncertainty are not established by two score files.",
                                             "Training recipes and capture isolation must be reviewed before attributing causality."]},
                        "Compatible evaluation comparison")
