from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from PIL import Image


class _LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in {"href", "src"} and value and not value.startswith(("#", "http:", "https:", "data:")):
                self.values.append(value)


def _finding(code: str, message: str, artifact: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, **({"artifact": artifact} if artifact else {})}


def _json(path: Path, findings: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(_finding("INVALID_JSON", f"{type(exc).__name__}: {exc}", path.name))
        return None


def _jsonl(path: Path, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            findings.append(_finding("INVALID_JSONL", f"line {number}: {exc}", path.name))
    return records


def inspect_pool(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).resolve()
    findings: list[dict[str, Any]] = []
    required = ["run.json", "summary.json", "samples.jsonl", "rejections.jsonl", "metrics.jsonl", "control.json", "control-events.jsonl", "qa/index.html"]
    for name in required:
        if not (root / name).is_file():
            findings.append(_finding("MISSING_ARTIFACT", f"Required artifact is missing: {name}", name))
    if findings:
        return {"schema_version": 1, "status": "invalid", "pool": str(root), "samples": 0, "findings": findings}

    manifest = _json(root / "run.json", findings)
    summary = _json(root / "summary.json", findings)
    control = _json(root / "control.json", findings)
    samples = _jsonl(root / "samples.jsonl", findings)
    _jsonl(root / "rejections.jsonl", findings)
    _jsonl(root / "metrics.jsonl", findings)
    _jsonl(root / "control-events.jsonl", findings)
    if manifest and summary:
        target = int(manifest.get("profile", {}).get("run", {}).get("num_images", -1))
        if int(summary.get("accepted_samples", -1)) != len(samples) or (summary.get("status") == "complete" and target != len(samples)):
            findings.append(_finding("SAMPLE_COUNT_DRIFT", "Manifest, summary, and samples.jsonl counts disagree"))
        if summary.get("contract_hash") != manifest.get("contract_hash"):
            findings.append(_finding("CONTRACT_HASH_DRIFT", "Summary and manifest contract hashes disagree"))
        expected_size = tuple(manifest.get("profile", {}).get("output", {}).get("image_size", ()))
        if len(expected_size) == 2:
            width, height = expected_size
            for sample in samples:
                image_path = root / str(sample.get("image_path", ""))
                try:
                    with Image.open(image_path) as image:
                        image.load()
                        if image.size != expected_size:
                            findings.append(_finding("IMAGE_DIMENSION_MISMATCH", f"Expected {expected_size}, got {image.size}", str(image_path.relative_to(root))))
                except Exception as exc:
                    findings.append(_finding("IMAGE_DECODE_FAILED", f"{type(exc).__name__}: {exc}", str(image_path.relative_to(root))))
                    continue
                for annotation in sample.get("annotations", []):
                    x1, y1, x2, y2 = annotation.get("bbox", (-1, -1, -1, -1))
                    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                        findings.append(_finding("ANNOTATION_OUT_OF_BOUNDS", f"Invalid bbox {annotation.get('bbox')}", sample.get("sample_id")))
                    nx, ny, nw, nh = annotation.get("normalized_bbox", (-1, -1, -1, -1))
                    if not (0 <= nx <= 1 and 0 <= ny <= 1 and 0 < nw <= 1 and 0 < nh <= 1):
                        findings.append(_finding("NORMALIZED_ANNOTATION_INVALID", f"Invalid normalized bbox {annotation.get('normalized_bbox')}", sample.get("sample_id")))
    if control and summary and control.get("actual_state") != summary.get("status"):
        findings.append(_finding("TERMINAL_STATE_DRIFT", "Control and summary terminal states disagree"))

    qa_index = root / "qa" / "index.html"
    parser = _LocalLinks()
    parser.feed(qa_index.read_text(encoding="utf-8"))
    for value in parser.values:
        if not (qa_index.parent / value).resolve().is_file():
            findings.append(_finding("BROKEN_QA_LINK", f"QA link does not resolve: {value}", f"qa/{value}"))
    return {
        "schema_version": 1,
        "status": "valid" if not findings else "invalid",
        "pool": str(root),
        "samples": len(samples),
        "qa_links": len(parser.values),
        "findings": findings,
    }
