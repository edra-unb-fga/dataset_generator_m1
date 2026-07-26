from __future__ import annotations

import json
import hashlib
import platform
from io import BytesIO
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import numpy as np
import yaml
from PIL import Image

from .assets import build_asset_catalog
from .backgrounds import BackgroundSynthesizer
from .config import load_profile, load_yaml_strict
from .generator import GenerationOptions, generate_pool
from .models import GenerationProfile, ResolvedProfile, RunConfig, VariantCatalog
from .scene import ScenePlanner, SceneRenderer, derive_seed


def validate_project(resolved: ResolvedProfile) -> dict[str, Any]:
    catalog = build_asset_catalog(resolved)
    return {
        "schema_version": 1,
        "status": "valid",
        "family": resolved.profile.family,
        "contract_hash": resolved.contract_hash,
        "recipes": sorted(resolved.recipes.recipes),
        "catalog": {
            "fingerprint": catalog.fingerprint,
            "backgrounds": len(catalog.backgrounds),
            "foregrounds": len(catalog.foregrounds),
            "classes": list(catalog.class_names),
            "background_group_counts": catalog.quality.background_group_counts,
            "foreground_group_counts": catalog.quality.foreground_group_counts,
            "class_counts": catalog.quality.class_counts,
            "exact_duplicate_groups": catalog.quality.exact_duplicate_groups,
            "perceptual_duplicate_groups": catalog.quality.perceptual_duplicate_groups,
        },
    }


def preview_backgrounds(resolved: ResolvedProfile, output_dir: str | Path, samples_per_recipe: int) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    catalog = build_asset_catalog(resolved)
    synthesizer = BackgroundSynthesizer(
        catalog,
        resolved.recipes,
        resolved.profile.assets.backgrounds.group_weights,
        resolved.profile.assets.backgrounds.asset_weights,
    )
    width, height = resolved.profile.output.image_size
    max_width = 640
    scale = min(1.0, max_width / width)
    size = (max(64, int(width * scale)), max(64, int(height * scale)))
    records: list[dict[str, Any]] = []
    for recipe_id in sorted(resolved.recipes.recipes):
        recipe_dir = output / recipe_id
        recipe_dir.mkdir(exist_ok=True)
        for index in range(samples_per_recipe):
            rng = np.random.default_rng(derive_seed(resolved.profile.run.seed, index, 0, f"preview-background:{recipe_id}"))
            sample = synthesizer.synthesize(recipe_id, size, rng)
            filename = f"{recipe_id}_{index:03d}.jpg"
            Image.fromarray(sample.image).save(recipe_dir / filename, quality=92)
            records.append(
                {
                    "recipe_id": recipe_id,
                    "recipe_version": sample.recipe_version,
                    "graph_hash": sample.graph_hash,
                    "index": index,
                    "image": f"{recipe_id}/{filename}",
                    "sources": list(sample.source_assets),
                    "node_timings_ns": sample.node_timings_ns,
                    "qa": sample.qa,
                    "warnings": list(sample.warnings),
                }
            )
    cards = "\n".join(
        f'<figure><img src="{record["image"]}" loading="lazy"><figcaption>{record["recipe_id"]} #{record["index"]}<pre>{json.dumps(record["qa"], indent=2)}</pre></figcaption></figure>'
        for record in records
    )
    html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>Background recipe preview</title>
<style>body{{font-family:system-ui;background:#111;color:#eee}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}img{{max-width:100%}}figure{{margin:0;background:#222;padding:10px}}pre{{white-space:pre-wrap}}</style></head><body><h1>Background recipes</h1><main>{cards}</main></body></html>"""
    (output / "index.html").write_text(html, encoding="utf-8")
    summary = {"schema_version": 1, "status": "complete", "samples": records, "output_dir": str(output)}
    (output / "preview.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def preview_scenes(
    config_path: str | Path,
    variants_path: str | Path | None,
    output_dir: str | Path,
    samples: int,
) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = load_profile(config_path)
    variants = {"base": {}}
    if variants_path:
        variants = VariantCatalog.model_validate(load_yaml_strict(variants_path)).variants
    results: dict[str, Any] = {}
    for name, overlay in variants.items():
        config = _deep_merge(base.profile.model_dump(mode="json"), overlay)
        config["run"] = {**config["run"], "label": f"{base.profile.run.label}-{name}", "num_images": samples}
        config["report"] = {**config["report"], "qa_samples": samples}
        profile = GenerationProfile.model_validate(config)
        contract_hash = hashlib.sha256(
            json.dumps({"base": base.contract_hash, "variant": name, "profile": profile.model_dump(mode="json")}, sort_keys=True).encode()
        ).hexdigest()
        resolved = base.model_copy(update={"profile": profile, "contract_hash": contract_hash})
        results[name] = generate_pool(resolved, output / name, GenerationOptions(display="quiet", workers=1))
    links = "".join(f'<li><a href="{name}/qa/index.html">{name}</a></li>' for name in results)
    (output / "index.html").write_text(f"<!doctype html><html><body><h1>Scene variants</h1><ul>{links}</ul></body></html>", encoding="utf-8")
    summary = {"schema_version": 1, "status": "complete", "variants": results, "output_dir": str(output)}
    (output / "preview.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def benchmark(resolved: ResolvedProfile, output_dir: str | Path, samples: int = 5, warmup: int = 1) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    catalog = build_asset_catalog(resolved)
    planner = ScenePlanner(resolved, catalog)
    renderer = SceneRenderer(resolved)
    synthesizer = BackgroundSynthesizer(catalog, resolved.recipes)
    records: list[dict[str, Any]] = []
    write_probe = output / ".benchmark-write.tmp"
    total = warmup + samples
    for index in range(total):
        timings: dict[str, int] = {}
        started = perf_counter_ns()
        plan = planner.plan(index, 0)
        timings["scene_plan"] = perf_counter_ns() - started
        started = perf_counter_ns()
        background = synthesizer.synthesize(
            plan.recipe_id,
            plan.canvas_size,
            np.random.default_rng(derive_seed(resolved.profile.run.seed, index, 0, "benchmark-background")),
        )
        timings["background_synthesis"] = perf_counter_ns() - started
        started = perf_counter_ns()
        rendered = renderer.render(plan, background)
        timings["scene_render"] = perf_counter_ns() - started
        started = perf_counter_ns()
        encoded = BytesIO()
        image_format = "JPEG" if resolved.profile.output.image_format in {"jpg", "jpeg"} else "PNG"
        save_options = {"quality": resolved.profile.output.jpeg_quality, "subsampling": 1} if image_format == "JPEG" else {}
        Image.fromarray(rendered.image).save(encoded, format=image_format, **save_options)
        payload = encoded.getvalue()
        timings["encoding"] = perf_counter_ns() - started
        started = perf_counter_ns()
        write_probe.write_bytes(payload)
        timings["writing"] = perf_counter_ns() - started
        if index >= warmup:
            records.append({"index": index - warmup, "timings_ns": timings, "annotations": len(rendered.annotations), "recipe_id": plan.recipe_id})
    stages = sorted({stage for record in records for stage in record["timings_ns"]})
    aggregate = {stage: {"mean_ns": int(np.mean([record["timings_ns"][stage] for record in records])), "p95_ns": int(np.percentile([record["timings_ns"][stage] for record in records], 95))} for stage in stages}
    write_probe.unlink(missing_ok=True)
    summary = {
        "schema_version": 1,
        "status": "complete",
        "contract_hash": resolved.contract_hash,
        "catalog_fingerprint": catalog.fingerprint,
        "environment": {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine()},
        "warmup": warmup,
        "samples": samples,
        "records": records,
        "stage_timings": aggregate,
    }
    (output / "benchmark.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _artifact_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_dir():
        for name in ("summary.json", "benchmark.json", "export.json", "preview.json"):
            candidate = source / name
            if candidate.exists():
                source = candidate
                break
    return json.loads(source.read_text(encoding="utf-8"))


def _number_delta(left: float | int | None, right: float | int | None) -> dict[str, float | None]:
    if left is None or right is None:
        return {"left": None if left is None else float(left), "right": None if right is None else float(right), "delta": None, "ratio": None}
    return {
        "left": float(left),
        "right": float(right),
        "delta": float(right - left),
        "ratio": float(right / left) if left else None,
    }


def _timing_comparison(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_stages = left.get("stage_timings", {})
    right_stages = right.get("stage_timings", {})
    result: dict[str, Any] = {}
    for stage in sorted(set(left_stages) | set(right_stages)):
        left_value = left_stages.get(stage, {}).get("p95_ns")
        right_value = right_stages.get(stage, {}).get("p95_ns")
        result[stage] = _number_delta(left_value, right_value)
    return result


def _count_changes(left: dict[str, Any], right: dict[str, Any], key: str) -> dict[str, Any]:
    left_values, right_values = left.get(key, {}), right.get(key, {})
    return {
        name: _number_delta(left_values.get(name, 0), right_values.get(name, 0))
        for name in sorted(set(left_values) | set(right_values))
    }


def compare_artifacts(left: str | Path, right: str | Path, output_dir: str | Path) -> dict[str, Any]:
    left_data, right_data = _artifact_json(left), _artifact_json(right)
    keys = sorted(set(left_data) | set(right_data))
    differences = {key: {"left": left_data.get(key), "right": right_data.get(key)} for key in keys if left_data.get(key) != right_data.get(key)}
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "status": "complete",
        "left": str(left),
        "right": str(right),
        "identity_changes": {
            key: {"left": left_data.get(key), "right": right_data.get(key)}
            for key in ("contract_hash", "catalog_fingerprint", "environment")
            if left_data.get(key) != right_data.get(key)
        },
        "timing_regressions": _timing_comparison(left_data, right_data),
        "rejection_changes": _count_changes(left_data, right_data, "rejection_reasons"),
        "class_distribution_changes": _count_changes(left_data, right_data, "class_counts"),
        "recipe_distribution_changes": _count_changes(left_data, right_data, "recipe_counts"),
        "resource_changes": _count_changes(left_data, right_data, "resource_peaks"),
        "differences": differences,
    }
    (output / "comparison.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rows = "".join(f"<tr><th>{key}</th><td><pre>{json.dumps(value['left'], indent=2)}</pre></td><td><pre>{json.dumps(value['right'], indent=2)}</pre></td></tr>" for key, value in differences.items())
    (output / "index.html").write_text(f"<!doctype html><html><body><h1>Artifact comparison</h1><table>{rows}</table></body></html>", encoding="utf-8")
    return summary
