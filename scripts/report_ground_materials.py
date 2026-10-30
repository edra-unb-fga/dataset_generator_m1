#!/usr/bin/env python3
"""Build a portable visual and measurement report for the ground material study."""
from __future__ import annotations

import argparse
import base64
import html
import importlib.util
import json
import re
from pathlib import Path

from PIL import Image

_HELPERS = Path(__file__).with_name("report_physical_combinations.py")
_spec = importlib.util.spec_from_file_location("physical_report_helpers", _HELPERS)
_helpers = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_helpers)
load_masks = _helpers.load_masks
compare_images = _helpers.compare_images
crop_box = _helpers.crop_box
embedded = _helpers.embedded

SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


def _safe_id(value: object, kind: str) -> str:
    value = str(value)
    if not SAFE_ID.fullmatch(value):
        raise ValueError(f"Unsafe {kind} ID: {value!r}")
    return value


def _matrix_cells(matrix: dict) -> list[dict]:
    cells = matrix.get("cells")
    if not isinstance(cells, list) or not cells:
        raise ValueError("Matrix must contain a non-empty cells list")
    ids = [_safe_id(c.get("id"), "cell") for c in cells]
    if len(ids) != len(set(ids)):
        raise ValueError("Matrix cell IDs must be unique")
    return cells


def _pair_identity(result: object) -> str | None:
    """Canonical render identity from the saved job and renderer camera evidence."""
    if not isinstance(result, dict):
        return None
    job = result.get("job")
    settings = result.get("renderer_settings")
    if not isinstance(job, dict) or not isinstance(settings, dict):
        return None
    ref = job.get("reference_scene_index")
    scene = job.get("scene")
    camera = {k: settings.get(k) for k in ("camera_to_world_opengl", "output_resolution")}
    camera["intrinsics_K_before_distortion"] = result.get("intrinsics_K_before_distortion")
    treatment = job.get("treatment") or {}
    camera["distortion_treatment"] = {k: treatment.get(k) for k in ("distortion", "distortion_strength", "distortion_seed") if k in treatment}
    if ref is None or scene is None or not camera["camera_to_world_opengl"] or camera["intrinsics_K_before_distortion"] is None:
        return None
    return json.dumps({"reference_scene_index": ref, "scene": scene, "camera": camera}, sort_keys=True, separators=(",", ":"))


def _baseline_id(cell: dict, available: set[str]) -> str | None:
    cid = cell["id"]
    if cid.startswith("context-"):
        return "context-full" if cid != "context-full" and "context-full" in available else None
    if cid.startswith("span-"):
        return "span-1" if cid != "span-1" and "span-1" in available else None
    if cid.startswith("g0-"):
        return "g0-full" if cid != "g0-full" else None
    if cid.startswith("g1-"):
        return "g1-full" if cid != "g1-full" else None
    if cid.startswith("indoor-"):
        return "indoor-full" if cid != "indoor-full" else None
    return None


def _asset_labels(study: dict, result: dict | None) -> list[str]:
    grounds = study.get("grounds", []) if isinstance(study, dict) else []
    if not isinstance(grounds, list):
        return []
    diag = (result or {}).get("surface_diagnostics") or {}
    job = (result or {}).get("job") or {}
    treatment = job.get("treatment") or {}
    material = treatment.get("ground_material") or diag.get("ground_material") or {}
    indices = []
    primary = material.get("primary_index")
    if primary is None:
        primary = diag.get("ground_index", job.get("ground_index"))
    donor = material.get("donor_index")
    if isinstance(primary, int): indices.append(primary)
    if isinstance(donor, int): indices.append(donor)
    labels = []
    for idx in dict.fromkeys(indices):
        label = f"ground[{idx}]"
        if 0 <= idx < len(grounds):
            item = grounds[idx]
            if isinstance(item, dict):
                provenance = item.get("provenance", {})
                label = str(provenance.get("asset_id") or label)
        labels.append(label)
    return labels


def _metric_record(root: Path, record: dict, cell: dict, asset_study: dict) -> tuple[dict, Image.Image | None, Image.Image | None, dict | None, dict | None]:
    cell_id = _safe_id(cell["id"], "cell")
    job = _safe_id(record.get("job", "missing"), "job")
    folder = root / cell_id / "scenes" / job
    out = {"cell": cell_id, "job": job, "status": "missing", "reason": None,
           "ground_assets": [], "environment": cell.get("environment"),
           "ground_mapping": cell.get("ground_mapping"), "ground_material": cell.get("treatment", {}).get("ground_material"),
           "ground_normal_strength": cell.get("treatment", {}).get("ground_normal_strength"),
           "shadows": cell.get("treatment", {}).get("shadows"), "casters": cell.get("treatment", {}).get("casters"),
           "ground_diagnostics": record.get("ground_diagnostics"),
           "environment_diagnostics": record.get("environment_diagnostics"),
           "command_seconds": (record.get("outcome") or {}).get("command_seconds"),
           "peak_resource": {k: v for k, v in (record.get("outcome") or {}).items() if "peak" in k.lower() or "memory" in k.lower()}}
    image = masks = result = None
    try:
        with Image.open(folder / "rgb.png") as source:
            image = source.convert("RGB")
        masks = load_masks(folder / "masks.npz")
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        out["status"] = result.get("status", "unknown")
        out["ground_assets"] = _asset_labels(asset_study, result)
        resolved_treatment = (result.get("job") or {}).get("treatment") or {}
        out["ground_normal_strength"] = resolved_treatment.get("ground_normal_strength", resolved_treatment.get("normal_strength", out["ground_normal_strength"]))
        out["shadows"] = resolved_treatment.get("shadows", out["shadows"])
        out["casters"] = resolved_treatment.get("casters", out["casters"])
        ground_diag = result.get("ground_diagnostics") or record.get("ground_diagnostics") or {}
        out["actual_ground_spans"] = ground_diag.get("achieved_spans")
        out["ground_diagnostics"] = ground_diag
        out["environment_diagnostics"] = result.get("environment_geometry_diagnostics") or record.get("environment_diagnostics")
        out["study_hash"] = record.get("identity")
        return out, image, masks, result, None
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        # Keep portable output free of absolute source paths from exception strings.
        out["reason"] = type(exc).__name__
        out["expected_output"] = f"{cell_id}/scenes/{job}/result.json or image/masks files"
        return out, None, None, None, None


def build(input_root: str | Path, matrix_path: str | Path, output: str | Path,
          metrics_output: str | Path | None = None) -> dict:
    root, output = Path(input_root), Path(output)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    matrix = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    cells = _matrix_cells(matrix)
    records = {r.get("cell", {}).get("id") if isinstance(r.get("cell"), dict) else r.get("cell"): r
               for r in summary.get("records", []) if isinstance(r, dict)}
    job_order = list(dict.fromkeys(_safe_id(r.get("job"), "job") for r in records.values() if r.get("job")))
    if not job_order:
        job_order = ["scene-0"]
    matrix_by_id = {c["id"]: c for c in cells}
    results, previews, crops, internal = [], {}, {}, {}
    record_by_id = {}
    for cell in cells:
        cid = cell["id"]
        record = records.get(cid)
        if record is None:
            record = {"cell": cell, "job": job_order[0], "status": "missing"}
        record_by_id[cid] = record
    for cell in cells:
        cid = cell["id"]
        record = record_by_id[cid]
        asset_study_path = root / cid / "study.json"
        try:
            asset_study = json.loads(asset_study_path.read_text(encoding="utf-8")) if asset_study_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            asset_study = {}
        metric, image, masks, render_result, _ = _metric_record(root, record, cell, asset_study)
        # Explicitly preserve failed/missing records even if their output folder is absent.
        if record.get("status") in ("failed", "error") and metric["status"] == "missing":
            metric["status"] = record.get("status")
        if image is not None:
            previews[cid] = embedded(image, 520, f"{cid} full image")
        internal[cid] = {"image": image, "masks": masks, "result": render_result}
        results.append(metric)

    # Compare each variant to its designated full baseline using actual saved camera and mask evidence.
    for metric in results:
        cid = metric["cell"]
        base_id = _baseline_id(matrix_by_id[cid], set(matrix_by_id))
        current, baseline = internal[cid], internal.get(base_id) if base_id else None
        if current["image"] is None or baseline is None or baseline["image"] is None:
            continue
        same_identity = (_pair_identity(current["result"]) is not None and
                         _pair_identity(current["result"]) == _pair_identity(baseline["result"]))
        if not same_identity:
            metric["paired"] = False
            metric["pairing_reason"] = "reference intent, camera transform, intrinsics, resolution, or distortion differs"
            continue
        comparison = compare_images(baseline["image"], current["image"], baseline["masks"], current["masks"])
        metric["mask_mismatch"] = not comparison["masks_equal"]
        metric["paired"] = bool(comparison["masks_equal"] and comparison["rgb_shape_match"])
        if metric["paired"]:
            metric.update(comparison)
            metric["comparison_baseline"] = base_id
            box = crop_box(baseline["masks"], baseline["image"].size)
            if box and current["image"].size == baseline["image"].size:
                crops[cid] = embedded(current["image"].crop(box), 360, f"{cid} baseline-mask matched crop")

    baseline_ids = {base for c in cells if (base := _baseline_id(c, set(matrix_by_id))) is not None}
    for metric in results:
        cid = metric["cell"]
        metric["comparison_role"] = "baseline" if cid in baseline_ids else "variant"
        if cid in baseline_ids and internal[cid]["image"] is not None:
            box = crop_box(internal[cid]["masks"], internal[cid]["image"].size)
            if box:
                crops[cid] = embedded(internal[cid]["image"].crop(box), 360, f"{cid} baseline-mask crop")

    safe_results = [{k: v for k, v in r.items() if k != "identity"} for r in results]
    payload = {"schema_version": 1, "status": summary.get("status", "unknown"),
               "matrix_purpose": matrix.get("purpose"), "metrics": safe_results}
    output.parent.mkdir(parents=True, exist_ok=True)
    destination = Path(metrics_output) if metrics_output else output.with_suffix(".metrics.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    rows = []
    for m in safe_results:
        vals = [m.get(k) for k in ("rgb_mae", "foreground_rgb_mae", "background_rgb_mae")]
        fmt = lambda v: "—" if v is None else f"{v:.2f}"
        rows.append("<tr><td>" + html.escape(m["cell"]) + "</td><td>" + html.escape(str(m["status"])) +
                    "</td><td>" + html.escape(", ".join(m["ground_assets"])) + "</td><td>" +
                    html.escape(str(m.get("ground_mapping"))) + "</td><td>" + html.escape(str(m.get("actual_ground_spans"))) + "</td><td>" + html.escape(str(m.get("ground_material"))) + "</td><td>" + html.escape(str(m.get("ground_normal_strength"))) + "</td><td>" + html.escape(str(m.get("shadows"))) +
                    "</td><td>" + ("matched" if m.get("paired") else "MASK MISMATCH" if m.get("mask_mismatch") else "baseline" if m.get("comparison_role")=="baseline" else "—") + "</td><td>" + " / ".join(map(fmt, vals)) +
                    "</td><td>" + fmt(m.get("command_seconds")) + "</td><td>" + html.escape(str(m.get("peak_resource") or "—")) + "</td></tr>")
    cards = []
    for m in safe_results:
        cid = m["cell"]
        cards.append(f'<article class="card" data-group="{html.escape(cid.split("-")[0], quote=True)}"><h3>{html.escape(cid)}</h3>'
                     f'<div class="images">{previews.get(cid, "<p>Image unavailable</p>")}{crops.get(cid, "<p>Matched crop unavailable</p>")}</div>'
                     f'<p>Status: {html.escape(str(m["status"]))}. Paired RGB metrics: {"available" if m.get("paired") else "baseline" if m.get("comparison_role")=="baseline" else "unavailable"}.</p>'
                     f'<details><summary>Diagnostics</summary><pre>{html.escape(json.dumps({k:m.get(k) for k in ("ground_diagnostics","environment_diagnostics","reason","pairing_reason") if m.get(k) is not None},indent=2))}</pre></details></article>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Ground material study</title>
<style>body{font:16px system-ui,sans-serif;max-width:1800px;margin:2rem auto;padding:0 1rem;color:#202832}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:.45rem;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#fff}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}.card{border:1px solid #ccc;border-radius:8px;padding:.8rem;min-width:0}.images{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}.images img{width:100%;height:auto;object-fit:contain}.note{background:#fff4d4;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>
<body><h1>Ground material study</h1><p class="note">RGB MAE describes pixel change relative to the designated paired baseline. It does not measure realism, utility, or statistical significance. Comparisons are included only when reference index, camera, and actual saved mask arrays match. Crops use the same baseline-derived visible-mask box. Images are reduced JPEG previews; inspect source PNGs for detail. Missing and failed outputs remain listed.</p>
<p>Study status: ''' + html.escape(str(payload["status"])) + '''. Use filters to focus the image grid.</p><h2>Measurements</h2><div style="overflow:auto"><table><thead><tr><th>Cell</th><th>Status</th><th>Source ground IDs</th><th>Requested mapping</th><th>Achieved spans</th><th>Material treatment</th><th>Ground normal strength</th><th>Shadows</th><th>Paired</th><th>Full / foreground / background RGB MAE</th><th>Command seconds</th><th>Peak resource</th></tr></thead><tbody>''' + "".join(rows) + '''</tbody></table></div>
<h2>Images</h2><label>Show <select id="group"><option value="all">all groups</option><option value="span">span</option><option value="g0">ground 0</option><option value="g1">ground 1</option><option value="indoor">indoor</option><option value="fixture">fixture</option></select></label><div class="cards">''' + "".join(cards) + '''</div>
<p><a href="''' + html.escape(destination.name, quote=True) + '''">Download measured JSON</a></p><script>document.getElementById('group').onchange=e=>{for(const c of document.querySelectorAll('.card'))c.hidden=e.target.value!=='all'&&c.dataset.group!==e.target.value}</script></body></html>'''
    output.write_text(page, encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Extracted results directory containing summary.json")
    parser.add_argument("--matrix", required=True, help="Tracked ground material matrix.json")
    parser.add_argument("--output", required=True, help="Self-contained HTML output")
    parser.add_argument("--metrics-output", help="Optional measured JSON output")
    args = parser.parse_args()
    build(args.input, args.matrix, args.output, args.metrics_output)


if __name__ == "__main__":
    main()
