from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .config import load_profile
from .generator import GenerationOptions, generate_pool
from .placement_diagnostics import summarize_placement_diagnostics
from .placement_diagnostics import clipped_sides as detect_clipped_sides
from .placement_diagnostics import spatial_region


@dataclass(frozen=True)
class PlacementStudyRequest:
    config: Path
    output_dir: Path
    samples: int = 200
    qa_samples: int = 20


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records), encoding="utf-8")


def _normalized_object_rejections(samples: list[dict[str, Any]], pool: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for sample in samples:
        matrix = np.asarray(sample["scene_to_output"], dtype=np.float64)
        image_size = sample.get("output_size")
        if image_size is None:
            with Image.open(pool / sample["image_path"]) as image:
                image_size = image.size
        width, height = image_size
        for original in sample.get("rejected_instances", []):
            record = dict(original)
            bbox = record.get("best_failed", {}).get("bbox")
            if bbox and not record.get("projected_bbox"):
                points = np.asarray(
                    [[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]]],
                    dtype=np.float32,
                )
                transformed = cv2.perspectiveTransform(points, matrix)[0]
                projected = [
                    float(transformed[:, 0].min()),
                    float(transformed[:, 1].min()),
                    float(transformed[:, 0].max()),
                    float(transformed[:, 1].max()),
                ]
                record["projected_bbox"] = [round(value, 3) for value in projected]
                record["clipped_sides"] = list(detect_clipped_sides(projected, width, height))
                record["region"] = spatial_region(
                    (projected[0] + projected[2]) / 2,
                    (projected[1] + projected[3]) / 2,
                    width,
                    height,
                )
            normalized.append(record)
    return normalized


def _accepted_object_attempts(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": item.get("source_asset", "unknown"),
            "class_name": item.get("class_name", "unknown"),
            "group": item.get("source_group", "unknown"),
            "scale": item.get("sampled_scale", 0.0),
            "rotation_degrees": item.get("sampled_rotation_degrees", 0.0),
            "requested_objects": item.get("requested_objects", sample.get("attempted_instances", 0)),
            "region": item.get("region", "unknown"),
            "stage": "accepted",
            "reason": "accepted",
        }
        for sample in samples
        for item in sample.get("annotations", [])
    ]


def _summary(generation: dict[str, Any], samples: list[dict[str, Any]], rejections: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": generation["status"],
        "accepted_samples": generation["accepted_samples"],
        "candidate_attempts": generation["candidate_attempts"],
        "diagnostics": summarize_placement_diagnostics(rejections, _accepted_object_attempts(samples)),
        "policy_changed": False,
    }


def _heatmap(records: list[dict[str, Any]], destination: Path) -> None:
    grid = np.zeros((8, 8), dtype=np.float32)
    for record in records:
        histogram = record.get("spatial_histogram", {})
        if histogram.get("bins") != 8 or len(histogram.get("counts", [])) != 64:
            continue
        grid += np.asarray(histogram["counts"], dtype=np.float32).reshape(8, 8)
    normalized = np.rint(grid / max(float(grid.max()), 1.0) * 255).astype(np.uint8)
    colored = cv2.applyColorMap(cv2.resize(normalized, (512, 512), interpolation=cv2.INTER_NEAREST), cv2.COLORMAP_INFERNO)
    Image.fromarray(cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)).save(destination)


def _report(samples: list[dict[str, Any]], records: list[dict[str, Any]], pool: Path, report: Path) -> None:
    gallery = report / "gallery"
    gallery.mkdir(parents=True, exist_ok=True)
    panels: list[Image.Image] = []
    cards: list[str] = []
    for sample in samples[:12]:
        source = pool / sample["image_path"]
        image = Image.open(source).convert("RGB")
        draw = ImageDraw.Draw(image)
        for record in sample.get("rejected_instances", []):
            bbox = record.get("clipped_bbox") or record.get("projected_bbox") or record.get("best_failed", {}).get("bbox")
            if bbox and not record.get("projected_bbox") and record.get("best_failed"):
                points = np.asarray(
                    [[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]]],
                    dtype=np.float32,
                )
                transformed = cv2.perspectiveTransform(points, np.asarray(sample["scene_to_output"], dtype=np.float64))[0]
                bbox = [
                    float(transformed[:, 0].min()),
                    float(transformed[:, 1].min()),
                    float(transformed[:, 0].max()),
                    float(transformed[:, 1].max()),
                ]
            if bbox:
                draw.rectangle(tuple(float(value) for value in bbox), outline=(255, 80, 80), width=3)
        target = gallery / f"{sample['sample_id']}.jpg"
        image.save(target, quality=88)
        panels.append(image.copy())
        cards.append(f'<figure><img src="gallery/{target.name}"><figcaption>{html.escape(sample["sample_id"])}</figcaption></figure>')
    if panels:
        thumb_w = 240
        thumbs = []
        for panel in panels:
            ratio = thumb_w / panel.width
            thumbs.append(panel.resize((thumb_w, max(1, int(panel.height * ratio)))))
        thumb_h = max(image.height for image in thumbs)
        sheet = Image.new("RGB", (thumb_w * min(4, len(thumbs)), thumb_h * ((len(thumbs) + 3) // 4)), (17, 24, 39))
        for index, image in enumerate(thumbs):
            sheet.paste(image, ((index % 4) * thumb_w, (index // 4) * thumb_h))
    else:
        sheet = Image.new("RGB", (640, 180), (17, 24, 39))
        ImageDraw.Draw(sheet).text((24, 72), "No accepted sample previews", fill=(240, 244, 248))
    sheet.save(report / "contact-sheet.jpg", quality=90)
    _heatmap(records, report / "spatial-heatmap.png")
    summary = summarize_placement_diagnostics(
        [record for record in records if str(record.get("stage", "")).startswith(("planner.", "renderer."))],
        _accepted_object_attempts(samples),
    )
    document = f"""<!doctype html><html><head><meta charset="utf-8"><title>Placement rejection study</title>
<style>body{{font-family:system-ui;background:#0b1220;color:#eef2f7;margin:24px}}img{{max-width:100%;height:auto}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}figure,pre{{background:#172033;padding:12px;margin:0;border-radius:8px}}pre{{overflow:auto}}</style></head><body>
<h1>Placement rejection study</h1><p>Production-path evidence; no placement policy was changed.</p>
<h2>Synchronized samples</h2><img src="contact-sheet.jpg" alt="placement contact sheet">
<h2>Attempted-position heatmap</h2><img src="spatial-heatmap.png" alt="spatial heatmap">
<h2>Summary</h2><pre>{html.escape(json.dumps(summary, indent=2))}</pre><main>{''.join(cards)}</main></body></html>"""
    (report / "index.html").write_text(document, encoding="utf-8")


def run_placement_study(request: PlacementStudyRequest) -> dict[str, Any]:
    if request.samples < 1 or request.qa_samples < 0:
        raise ValueError("samples must be positive and qa-samples cannot be negative")
    if request.output_dir.exists() and any(request.output_dir.iterdir()):
        raise ValueError(f"Study output directory is not empty: {request.output_dir}")
    resolved = load_profile(
        request.config,
        {"run.num_images": request.samples, "report.qa_samples": min(request.qa_samples, request.samples)},
    )
    request.output_dir.mkdir(parents=True, exist_ok=True)
    pool = request.output_dir / "pool"
    generation = generate_pool(
        resolved,
        pool,
        GenerationOptions(display="quiet", workers=1, qa_samples=min(request.qa_samples, request.samples)),
    )
    samples = _read_jsonl(pool / "samples.jsonl")
    candidate_rejections = _read_jsonl(pool / "rejections.jsonl")
    object_rejections = _normalized_object_rejections(samples, pool)
    records = [*object_rejections, *candidate_rejections]
    summary = _summary(generation, samples, object_rejections)
    study = {
        "schema_version": 1,
        "kind": "placement-rejection-diagnostics",
        "config": request.config.name,
        "samples": request.samples,
        "qa_samples": request.qa_samples,
        "pool": "pool",
        "report": "report/index.html",
        "contract_hash": resolved.contract_hash,
    }
    _write_json(request.output_dir / "study.json", study)
    _write_jsonl(request.output_dir / "rejections.jsonl", records)
    _write_json(request.output_dir / "summary.json", summary)
    _report(samples, records, pool, request.output_dir / "report")
    return {**summary, "study_path": str(request.output_dir / "study.json"), "report_path": str(request.output_dir / "report" / "index.html")}


def validate_placement_study(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    required = ("study.json", "rejections.jsonl", "summary.json", "report/index.html")
    missing = [name for name in required if not (root / name).is_file()]
    errors = [f"missing {name}" for name in missing]
    if not missing:
        study = json.loads((root / "study.json").read_text(encoding="utf-8"))
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        if study.get("samples") != summary.get("accepted_samples"):
            errors.append("study sample count does not match summary")
        report_path = root / "report" / "index.html"
        document = report_path.read_text(encoding="utf-8")
        for target in re.findall(r'(?:src|href)="([^"]+)"', document):
            if "://" not in target and not (report_path.parent / target).is_file():
                errors.append(f"broken report link: {target}")
    return {"status": "invalid" if errors else "valid", "errors": errors}


def rebuild_placement_study(output_dir: str | Path) -> dict[str, Any]:
    """Rebuild derived study evidence from an already committed production pool."""
    root = Path(output_dir)
    pool = root / "pool"
    samples = _read_jsonl(pool / "samples.jsonl")
    generation = json.loads((pool / "summary.json").read_text(encoding="utf-8"))
    object_rejections = _normalized_object_rejections(samples, pool)
    candidate_rejections = _read_jsonl(pool / "rejections.jsonl")
    summary = _summary(generation, samples, object_rejections)
    records = [*object_rejections, *candidate_rejections]
    _write_jsonl(root / "rejections.jsonl", records)
    _write_json(root / "summary.json", summary)
    _report(samples, records, pool, root / "report")
    return summary
