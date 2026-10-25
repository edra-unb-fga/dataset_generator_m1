"""Small offline analytical artifacts shared by evaluation and reference workflows."""
from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("JSON number exceeds finite range")
        return result

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=nonfinite, parse_float=finite_float)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fresh_output(path):
    path = Path(path).resolve()
    if path.exists() and any(path.iterdir()):
        raise ValueError("Analysis output directory must be empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_artifact(root, relative):
    candidate = (Path(root) / relative).resolve()
    try:
        candidate.relative_to(Path(root).resolve())
    except ValueError as exc:
        raise ValueError("Artifact path must remain inside its declared root") from exc
    return candidate


def write_report(output, result, title, *, images=(), filename="summary.json"):
    output = Path(output)
    serialized = json.dumps(result, indent=2, allow_nan=False)
    (output / filename).write_text(serialized + "\n", encoding="utf-8")
    cards = "".join(
        f'<figure><img loading="lazy" src="{html.escape(path, quote=True)}" alt="{html.escape(label, quote=True)}">'
        f'<figcaption>{html.escape(label)}</figcaption></figure>' for path, label in images
    )
    warnings = "".join(f"<li>{html.escape(str(w))}</li>" for w in result.get("warnings", []))
    def table(headers, rows):
        cells = lambda values, tag: "".join(f"<{tag}>{html.escape(str(value) if value is not None else 'unavailable')}</{tag}>" for value in values)
        return "<table><thead><tr>" + cells(headers, "th") + "</tr></thead><tbody>" + "".join("<tr>" + cells(row, "td") + "</tr>" for row in rows) + "</tbody></table>"

    tables = ""
    if result.get("kind") == "evaluation-score":
        tables += table(["Task", "AP", "AP50", "AP75", "AR100", "TP", "FP", "FN"], [
            [task, *[round(values["metrics"][key], 4) if values["metrics"][key] is not None else None for key in ("AP", "AP50", "AP75", "AR100")],
             *[values["operating_point"][key] for key in ("tp", "fp", "fn")]] for task, values in result["tasks"].items()])
        tables += table(["Task", "Class", "GT instances", "AP"], [
            [task, row["name"], row["ground_truth_instances"], round(row["AP"], 4) if row["AP"] is not None else None]
            for task, values in result["tasks"].items() for row in values["per_class"]])
    if result.get("kind") == "reference-audit":
        tables += table(["Image", "Dimensions", "Targets", "Mean luma", "Sharpness proxy", "Session"], [
            [row["id"], row["image_size"], len(row["targets"]), round(row["observables"]["mean_luma_8bit"], 2),
             round(row["observables"]["laplacian_variance_proxy"], 2), row["capture_session"]] for row in result["images"]])
    (output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f'<title>{html.escape(title)}</title><style>body{{max-width:1200px;margin:auto;padding:24px;font:16px/1.5 system-ui;'
        'background:#f5f5f2;color:#182532}h1{line-height:1.2}.images{display:flex;flex-wrap:wrap;gap:16px}'
        'figure{margin:0;max-width:520px}img{width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
        'background:white;padding:16px}a{color:#075e91}table{border-collapse:collapse;margin:24px 0;display:block;overflow:auto}'
        'td,th{padding:8px 14px;text-align:left;border-bottom:1px solid #c5cece}th{background:#e5ece8}</style>'
        f'<h1>{html.escape(title)}</h1><p>Inspect the measurements, provenance and limitations below. '
        'Synthetic correctness and visual plausibility do not establish real-image model accuracy.</p>'
        f'<ul>{warnings}</ul>{tables}<p><a href="{html.escape(filename)}">Machine-readable evidence</a></p>'
        f'<div class="images">{cards}</div><h2>Measurements and provenance</h2><pre>{html.escape(serialized)}</pre></html>',
        encoding="utf-8",
    )
    return result
