from __future__ import annotations

import argparse
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_pool(root: Path) -> dict[str, Any]:
    required = [
        "run.json",
        "summary.json",
        "samples.jsonl",
        "rejections.jsonl",
        "metrics.jsonl",
        "control.json",
        "control-events.jsonl",
        "qa/index.html",
    ]
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"Missing pool artifacts: {', '.join(missing)}")

    manifest = json.loads((root / "run.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    samples = _read_jsonl(root / "samples.jsonl")
    if summary.get("status") != "complete":
        raise ValueError(f"Pool is not complete: {summary.get('status')}")
    if summary.get("accepted_samples") != len(samples):
        raise ValueError("summary accepted_samples does not match samples.jsonl")
    target = int(manifest["profile"]["run"]["num_images"])
    if len(samples) != target:
        raise ValueError(f"Expected {target} samples, found {len(samples)}")

    expected_size = tuple(manifest["profile"]["output"]["image_size"])
    for sample in samples:
        image_path = root / sample["image_path"]
        with Image.open(image_path) as image:
            image.load()
            if image.size != expected_size:
                raise ValueError(f"Unexpected dimensions for {image_path}: {image.size}")
        width, height = expected_size
        for annotation in sample.get("annotations", []):
            x1, y1, x2, y2 = annotation["bbox"]
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError(f"Out-of-bounds annotation in {sample['sample_id']}: {annotation['bbox']}")
            nx, ny, nw, nh = annotation["normalized_bbox"]
            if not (0 <= nx <= 1 and 0 <= ny <= 1 and 0 < nw <= 1 and 0 < nh <= 1):
                raise ValueError(f"Invalid normalized annotation in {sample['sample_id']}")

    qa_index = root / "qa" / "index.html"
    parser = _LocalLinks()
    parser.feed(qa_index.read_text(encoding="utf-8"))
    broken = [value for value in parser.values if not (qa_index.parent / value).resolve().is_file()]
    if broken:
        raise ValueError(f"Broken QA links: {', '.join(broken)}")
    return {"status": "valid", "pool": root.as_posix(), "samples": len(samples), "qa_links": len(parser.values)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify compact CI pool evidence.")
    parser.add_argument("pool", type=Path)
    result = verify_pool(parser.parse_args().pool.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
