"""Normalize external annotations and existing generator evidence without model runtimes."""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

from .analysis_reports import digest, file_hash, fresh_output, local_artifact, read_json, write_report
from .annotation_evidence import decode_mask_evidence
from .inspection import inspect_pool
from .analysis_contracts import EvaluationManifest


def mask_backend():
    try:
        from pycocotools import mask
    except ImportError as exc:
        raise ValueError("Evaluation requires the optional extra: uv sync --extra evaluation") from exc
    return mask


def encode_mask(mask):
    encoded = mask_backend().encode(np.asfortranarray(mask, dtype=np.uint8))
    return {"size": [int(x) for x in encoded["size"]], "counts": encoded["counts"].decode("ascii")}


def instance_mask(segmentation, width, height):
    backend = mask_backend()
    if isinstance(segmentation, list):
        if not segmentation or any(not isinstance(p, list) or len(p) < 6 or len(p) % 2 for p in segmentation):
            raise ValueError("Segmentation polygons require at least three coordinate pairs")
        for polygon in segmentation:
            for x, y in zip(polygon[::2], polygon[1::2]):
                if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)):
                    raise ValueError("Polygon coordinates must be finite numbers")
                if not (0 <= x <= width and 0 <= y <= height):
                    raise ValueError("Polygon coordinates are outside the image")
        encoded = backend.merge(backend.frPyObjects(segmentation, height, width))
    elif isinstance(segmentation, dict):
        if segmentation.get("size") != [height, width]:
            raise ValueError("RLE dimensions do not match the image")
        counts = segmentation.get("counts")
        if isinstance(counts, list):
            if any(type(v) is not int or v < 0 for v in counts) or sum(counts) != width * height:
                raise ValueError("Invalid uncompressed RLE run lengths")
            encoded = backend.frPyObjects(segmentation, height, width)
        elif isinstance(counts, str):
            encoded = {"size": [height, width], "counts": counts.encode("ascii")}
        else:
            raise ValueError("Invalid RLE counts")
    else:
        raise ValueError("Segmentation must be COCO polygons or RLE")
    try:
        decoded = backend.decode(encoded)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid segmentation encoding") from exc
    if decoded.shape != (height, width) or not np.any(decoded):
        raise ValueError("Instance segmentation must be a nonempty image-sized mask")
    return decoded.astype(bool)


def valid_box(value, width, height):
    if not isinstance(value, list) or len(value) != 4 or any(
        not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in value
    ):
        raise ValueError("COCO bbox must contain four finite pixel xywh values")
    x, y, w, h = value
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width + 1e-6 or y + h > height + 1e-6:
        raise ValueError("BBox must have positive area and lie inside the image")
    return [float(v) for v in value]


def _unique_ids(rows, name):
    ids = [r.get("id") for r in rows]
    if any(type(v) is not int or v < 0 for v in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"{name} need unique nonnegative integer IDs")


def validate_coco(coco, *, predictions=False):
    for key in ("images", "categories", "annotations"):
        if not isinstance(coco.get(key), list):
            raise ValueError(f"COCO dataset requires {key}")
        _unique_ids(coco[key], key)
    if not coco["images"] or not coco["categories"]:
        raise ValueError("Evaluation requires images and declared classes")
    images = {r["id"]: r for r in coco["images"]}
    categories = {r["id"] for r in coco["categories"]}
    names = [r.get("name") for r in coco["categories"]]
    if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        raise ValueError("Category names must be unique nonempty strings")
    filenames = []
    for image in images.values():
        if any(type(image.get(k)) is not int or image[k] <= 0 for k in ("width", "height")):
            raise ValueError("Image dimensions must be positive integers")
        if not isinstance(image.get("file_name"), str) or not image["file_name"]:
            raise ValueError("Image file_name is required")
        filenames.append(image["file_name"])
    if len(set(filenames)) != len(filenames):
        raise ValueError("Image paths must be unique; basenames alone are not identities")
    for annotation in coco["annotations"]:
        if annotation.get("image_id") not in images or annotation.get("category_id") not in categories:
            raise ValueError("Annotation references an unknown image or class")
        image = images[annotation["image_id"]]
        annotation["bbox"] = valid_box(annotation.get("bbox"), image["width"], image["height"])
        if annotation.get("iscrowd", 0) not in (0, 1):
            raise ValueError("iscrowd must be 0 or 1")
        annotation.setdefault("iscrowd", 0)
        if "segmentation" in annotation:
            mask = instance_mask(annotation["segmentation"], image["width"], image["height"])
            annotation["segmentation"] = encode_mask(mask)
            annotation.setdefault("area", int(mask.sum()))
        else:
            annotation.setdefault("area", annotation["bbox"][2] * annotation["bbox"][3])
        if not isinstance(annotation["area"], (int, float)) or not math.isfinite(annotation["area"]) or annotation["area"] <= 0:
            raise ValueError("Annotation area must be positive and finite")
    return coco


def _pool_rows(pool):
    if inspect_pool(pool)["status"] != "valid":
        raise ValueError("Source pool failed inspection")
    run = read_json(pool / "run.json")
    rows = [json.loads(line) for line in (pool / "samples.jsonl").read_text().splitlines() if line.strip()]
    return run, rows


def _from_pool(pool, semantics):
    run, rows = _pool_rows(pool)
    classes = run["family"]["classes"]
    coco = {"images": [], "categories": [{"id": i, "name": n} for i, n in enumerate(classes)], "annotations": []}
    sources, metadata = {}, {}
    for image_id, row in enumerate(rows, 1):
        path = local_artifact(pool, row["image_path"])
        with Image.open(path) as image:
            width, height = image.size
        coco["images"].append({"id": image_id, "file_name": row["image_path"], "width": width, "height": height})
        sources[image_id] = path
        metadata[str(image_id)] = {
            "sample_id": row["sample_id"], "geometry_signature": row["geometry_signature"],
            "recipe_id": row.get("background_recipe"), "scene_effects": row.get("scene_effects", {}),
            "perspective_quad": row.get("perspective_quad"), "camera_rect": row.get("camera_rect"),
            "effect_traces": row.get("effects", []),
            "conditions_provenance": "configured-and-sampled-synthetic; not physical calibration",
        }
        evidence = row.get("mask_evidence")
        decoded = decode_mask_evidence(local_artifact(pool, evidence["path"]).read_bytes(), evidence) if evidence else {}
        threshold = int(evidence["alpha_threshold"]) if evidence else 8
        for a in row["annotations"]:
            x1, y1, x2, y2 = a["bbox"]
            item = {"id": len(coco["annotations"]) + 1, "image_id": image_id, "category_id": classes.index(a["class_name"]),
                    "bbox": [x1, y1, x2-x1, y2-y1], "iscrowd": 0,
                    "source_instance_id": a.get("instance_id"), "source_content_hash": a.get("source_content_hash"),
                    "visible_bbox_fraction": a.get("visible_bbox_fraction"),
                    "visible_support_fraction": a.get("visible_support_fraction")}
            if a.get("instance_id") in decoded:
                mask = decoded[a["instance_id"]][semantics] > threshold
                item["segmentation"] = encode_mask(mask)
                item["area"] = int(mask.sum())
            coco["annotations"].append(item)
    return coco, sources, metadata, {"run_manifest_sha256": file_hash(pool / "run.json"), "mask_reference": "exact-pool"}


def _from_export(root, spec, manifest_root):
    export = read_json(root / "export.json")
    split = spec.get("split")
    if split not in export["splits"]:
        raise ValueError("An existing export split must be selected explicitly")
    classes = export["classes"]
    coco = {"images": [], "categories": [{"id": i, "name": n} for i, n in enumerate(classes)], "annotations": []}
    sources, metadata, bindings = {}, {}, {}
    for name, location in spec.get("pool_bindings", {}).items():
        pool = (manifest_root / location).resolve()
        identity = next((r for r in export["source_pools"] if r["pool_id"] == name), None)
        if identity is None or identity["run_manifest_sha256"] != file_hash(pool / "run.json"):
            raise ValueError("Source pool binding does not match the export manifest hash")
        bindings[name] = _from_pool(pool, spec.get("annotation_semantics", "visible"))
    for image_id, row in enumerate((r for r in export["samples"] if r["split"] == split), 1):
        path = local_artifact(root, f"images/{split}/{row['filename']}")
        with Image.open(path) as image:
            width, height = image.size
        coco["images"].append({"id": image_id, "file_name": f"images/{split}/{row['filename']}", "width": width, "height": height})
        sources[image_id] = path
        metadata[str(image_id)] = {k: row[k] for k in ("sample_id", "pool_sample_key", "source_pool_id")}
        if bindings:
            if row["source_pool_id"] not in bindings:
                raise ValueError("Pool bindings must cover every selected source pool")
            pc, ps, pm, _ = bindings[row["source_pool_id"]]
            source_id = next((int(k) for k, v in pm.items() if v["sample_id"] == row["sample_id"]), None)
            if source_id is None or file_hash(ps[source_id]) != file_hash(path):
                raise ValueError("Exported image does not match its bound source sample")
            metadata[str(image_id)].update(pm[str(source_id)])
            for item in pc["annotations"]:
                if item["image_id"] == source_id:
                    item = dict(item, id=len(coco["annotations"])+1, image_id=image_id,
                                category_id=classes.index(pc["categories"][item["category_id"]]["name"]))
                    coco["annotations"].append(item)
            continue
        label = local_artifact(root, f"labels/{split}/{Path(row['filename']).stem}.txt")
        for line in label.read_text().splitlines():
            if not line.strip():
                continue
            values = [float(v) for v in line.split()]
            if len(values) < 5 or not values[0].is_integer() or not 0 <= values[0] < len(classes):
                raise ValueError("Invalid YOLO class or label shape")
            item = {"id": len(coco["annotations"])+1, "image_id": image_id, "category_id": int(values[0]), "iscrowd": 0}
            if export["task"] == "detection":
                if len(values) != 5:
                    raise ValueError("Detection export requires five-column labels")
                _, cx, cy, w, h = values
                item["bbox"] = [(cx-w/2)*width, (cy-h/2)*height, w*width, h*height]
            else:
                if len(values) < 7 or len(values) % 2 != 1:
                    raise ValueError("Invalid YOLO segmentation polygon")
                polygon = [v * (width if i % 2 == 0 else height) for i, v in enumerate(values[1:])]
                item["segmentation"] = [polygon]
                xs, ys = polygon[::2], polygon[1::2]
                item["bbox"] = [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]
            coco["annotations"].append(item)
    return coco, sources, metadata, {"export_manifest_sha256": file_hash(root / "export.json"),
                                    "export_fidelity": export.get("fidelity"),
                                    "mask_reference": "exact-pool" if bindings else "exported-labels"}


def prepare_dataset(manifest_file, output_dir):
    manifest_file = Path(manifest_file).resolve()
    spec = EvaluationManifest.model_validate(read_json(manifest_file)).model_dump(exclude_none=True)
    if spec.get("schema_version") != 1 or spec.get("domain") not in {"real", "synthetic"} or spec.get("role") not in {"development", "held-out", "regression"}:
        raise ValueError("Evaluation manifest needs schema_version 1, explicit domain and evaluation role")
    semantics = spec.get("annotation_semantics", "unknown")
    if semantics not in {"visible", "full", "unknown"}:
        raise ValueError("annotation_semantics must be visible, full or unknown")
    root = (manifest_file.parent / spec.get("source", ".")).resolve()
    if spec.get("format") == "pool":
        if semantics == "unknown":
            raise ValueError("Pool annotation semantics must be explicitly visible or full")
        coco, sources, metadata, provenance = _from_pool(root, semantics)
    elif spec.get("format") == "yolo-export":
        if spec.get("pool_bindings") and semantics == "unknown":
            raise ValueError("Bound mask semantics must be visible or full")
        coco, sources, metadata, provenance = _from_export(root, spec, manifest_file.parent)
    elif spec.get("format") == "coco":
        gt = local_artifact(root, spec.get("ground_truth", "annotations.json"))
        coco = read_json(gt)
        image_root = (root / spec.get("images_root", ".")).resolve()
        sources = {r["id"]: local_artifact(image_root, r["file_name"]) for r in coco["images"]}
        metadata, provenance = {}, {"ground_truth_sha256": file_hash(gt), "mask_reference": "supplied-coco"}
    else:
        raise ValueError("format must be coco, pool or yolo-export")
    validate_coco(coco)
    for row in coco["images"]:
        with Image.open(sources[row["id"]]) as image:
            if image.size != (row["width"], row["height"]):
                raise ValueError("Declared image dimensions do not match image pixels")
        row["sha256"] = file_hash(sources[row["id"]])
    if spec.get("metadata_file"):
        extra = read_json(manifest_file.parent / spec["metadata_file"])
        if not isinstance(extra, dict) or any(k not in {str(r["id"]) for r in coco["images"]} for k in extra):
            raise ValueError("Metadata sidecar must map known image IDs to objects")
        for key, value in extra.items():
            if not isinstance(value, dict):
                raise ValueError("Image metadata must be objects")
            metadata.setdefault(key, {}).update(value)
    output = fresh_output(output_dir)
    (output / "images").mkdir()
    cards = []
    for row in coco["images"]:
        path = sources[row["id"]]
        row["source_relative_image"] = row["file_name"]
        row["file_name"] = f"images/{row['id']}{path.suffix.lower()}"
        shutil.copy2(path, output / row["file_name"])
        if len(cards) < 12:
            cards.append((row["file_name"], f"Image {row['id']}"))
    coco["info"] = {"description": "Normalized evaluation ground truth"}
    warnings = ["Capture-session independence and real-world calibration are unknown unless explicitly evidenced."]
    if provenance["mask_reference"] == "exported-labels":
        warnings.append("Exact pool masks were not bound; segmentation reference is the lossy exported representation.")
    if semantics == "unknown":
        warnings.append("Annotation semantics are unknown; cross-policy comparisons must not claim equivalence.")
    result = {"schema_version": 1, "status": "complete_with_warnings", "kind": "evaluation-dataset",
              "domain": spec["domain"], "role": spec["role"], "annotation_semantics": semantics,
              "ground_truth": coco, "metadata": metadata, "provenance": provenance,
              "training_provenance": spec.get("training_provenance", "unknown"), "warnings": warnings,
              "support": dict(Counter(a["category_id"] for a in coco["annotations"]))}
    result["dataset_sha256"] = digest({k: v for k, v in result.items() if k not in {"status", "warnings"}})
    return write_report(output, result, "Prepared evaluation dataset", images=cards, filename="dataset.json")
