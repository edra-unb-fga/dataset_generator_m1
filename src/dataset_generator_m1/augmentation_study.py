from __future__ import annotations

import hashlib
import html
import json
import platform
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from statistics import mean
from time import perf_counter_ns
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageOps
from pydantic import BaseModel, ConfigDict, Field

from .assets import build_asset_catalog
from .backgrounds import BackgroundSynthesisError, BackgroundSynthesizer
from .config import load_appearance_profile, load_profile, load_yaml_strict
from .filters import backend_version, validate_appearance
from .models import AppearanceConfig, ResolvedProfile, TransformSpec
from .scene import ScenePlan, ScenePlanner, SceneRejected, SceneRenderer, derive_seed


DEFAULT_STUDY_DEFINITION = Path(__file__).parents[2] / "examples" / "experiments" / "augmentation_study.yaml"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AugmentationMatrix(_StrictModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    treatments: dict[str, AppearanceConfig]


@dataclass(frozen=True)
class AugmentationStudyRequest:
    config: Path
    output_dir: Path
    matrix: Path | None = None
    study_definition: Path = DEFAULT_STUDY_DEFINITION
    warmups: int = 2
    samples: int = 20
    include_stress: bool = False


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_json(payload: Any) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def _git_identity(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except Exception:
        return {"commit": "unknown", "dirty": None}


def _require_ids(appearance: AppearanceConfig, treatment: str) -> None:
    for stage in ("background", "foreground", "final"):
        specs = getattr(appearance, stage)
        missing = [index for index, spec in enumerate(specs) if not spec.id]
        if missing:
            raise ValueError(f"Treatment {treatment}.{stage} requires stable transform IDs at indices {missing}")
    validate_appearance(appearance.background, appearance.foreground, appearance.final)


def _load_appearance(raw: dict[str, Any]) -> AppearanceConfig:
    return AppearanceConfig.model_validate(raw)


def _append_appearance(base: AppearanceConfig, extra: AppearanceConfig) -> AppearanceConfig:
    return AppearanceConfig(
        background=(*base.background, *extra.background),
        foreground=(*base.foreground, *extra.foreground),
        final=(*base.final, *extra.final),
    )


def _stage_only(base: AppearanceConfig, extra: AppearanceConfig, stage: str) -> AppearanceConfig:
    values = {
        "background": base.background,
        "foreground": base.foreground,
        "final": base.final,
    }
    values[stage] = (*values[stage], *getattr(extra, stage))
    return AppearanceConfig(**values)


def resolve_treatments(
    resolved: ResolvedProfile,
    study_definition: str | Path = DEFAULT_STUDY_DEFINITION,
    matrix: str | Path | None = None,
    include_stress: bool = False,
) -> tuple[dict[str, AppearanceConfig], dict[str, Any]]:
    """Resolve and validate appearance-only treatments before output is created."""
    if matrix:
        parsed = AugmentationMatrix.model_validate(load_yaml_strict(matrix))
        treatments = dict(parsed.treatments)
        metadata = {"source": str(Path(matrix)), "custom_matrix": True}
    else:
        definition_path = Path(study_definition)
        definition = load_yaml_strict(definition_path)
        legacy_path = Path(__file__).parents[2] / str(definition["legacy"]["archival_file"])
        legacy_raw = load_yaml_strict(legacy_path)
        legacy = _load_appearance(legacy_raw["appearance"])
        realistic = _load_appearance(definition["realistic_heavy"])
        # `current` is the historical compact stack. Shipped composers now default to
        # realistic-heavy, so resolving it explicitly preserves the paired study meaning.
        current = load_appearance_profile("builtin:appearance/current-fast", resolved.config_path)
        treatments = {
            "no-appearance": AppearanceConfig(),
            "current": current,
            "legacy-heavy-compatible": legacy,
            "realistic-heavy-background": _stage_only(current, realistic, "background"),
            "realistic-heavy-foreground": _stage_only(current, realistic, "foreground"),
            "realistic-heavy-final": _stage_only(current, realistic, "final"),
            "realistic-heavy-combined": _append_appearance(current, realistic),
        }
        if include_stress:
            forced = AppearanceConfig(
                background=tuple(spec.model_copy(update={"probability": 1.0}) for spec in legacy.background),
                foreground=tuple(spec.model_copy(update={"probability": 1.0}) for spec in legacy.foreground),
                final=tuple(spec.model_copy(update={"probability": 1.0}) for spec in legacy.final),
            )
            treatments["all-effects-stress"] = forced
        metadata = {
            "source": str(definition_path),
            "custom_matrix": False,
            "legacy_source_commit": definition["legacy"]["source_commit"],
            "unsupported_translation": definition["legacy"]["unsupported_translation"],
        }
    if not treatments:
        raise ValueError("Augmentation study requires at least one treatment")
    for name, appearance in treatments.items():
        if not name or name.startswith(".") or "/" in name or "\\" in name:
            raise ValueError(f"Invalid treatment name: {name!r}")
        _require_ids(appearance, name)
    return treatments, metadata


def balanced_treatment_order(names: tuple[str, ...], fixture_index: int) -> tuple[str, ...]:
    if not names:
        return ()
    offset = fixture_index % len(names)
    order = (*names[offset:], *names[:offset])
    return tuple(reversed(order)) if (fixture_index // len(names)) % 2 else tuple(order)


def _annotation_signature(rendered: Any) -> str:
    return _sha256_json(
        [
            {
                "class_id": item.class_id,
                "bbox": item.bbox,
                "normalized_bbox": [round(value, 12) for value in item.normalized_bbox],
                "source": item.source_asset,
            }
            for item in rendered.annotations
        ]
    )


def _mask_signature(rendered: Any) -> str:
    digest = hashlib.sha256()
    for mask in rendered.instance_masks:
        digest.update(mask.tobytes())
    return digest.hexdigest()


def _profile_with_appearance(resolved: ResolvedProfile, appearance: AppearanceConfig) -> ResolvedProfile:
    return resolved.model_copy(update={"profile": resolved.profile.model_copy(update={"appearance": appearance})})


def _encode(image: np.ndarray, resolved: ResolvedProfile, clock: Callable[[], int]) -> tuple[bytes, int]:
    started = clock()
    buffer = BytesIO()
    image_format = "JPEG" if resolved.profile.output.image_format in {"jpg", "jpeg"} else "PNG"
    options = {"quality": resolved.profile.output.jpeg_quality, "subsampling": 1} if image_format == "JPEG" else {}
    Image.fromarray(image).save(buffer, format=image_format, **options)
    return buffer.getvalue(), max(0, clock() - started)


def _percentile(values: list[int], quantile: float) -> int:
    return int(np.percentile(values, quantile)) if values else 0


def _summarize(records: list[dict[str, Any]], samples: int) -> dict[str, Any]:
    by_treatment: dict[str, dict[str, Any]] = {}
    for treatment in sorted({record["treatment"] for record in records}):
        selected = [record for record in records if record["treatment"] == treatment]
        render_values = [record["render_only_ns"] for record in selected]
        modeled_values = [record["modeled_production_ns"] for record in selected]
        effect_rows = [effect for record in selected for effect in record["effects"] if effect["applied"]]
        effect_groups: dict[str, list[int]] = {}
        for effect in effect_rows:
            effect_groups.setdefault(effect["id"], []).append(effect["duration_ns"])
        by_treatment[treatment] = {
            "calls": len(selected),
            "render_total_ns": sum(render_values),
            "render_mean_ns": int(mean(render_values)),
            "render_p95_ns": _percentile(render_values, 95),
            "modeled_mean_ns": int(mean(modeled_values)),
            "modeled_p95_ns": _percentile(modeled_values, 95),
            "per_object_mean_ns": int(sum(render_values) / max(1, sum(record["object_count"] for record in selected))),
            "per_megapixel_mean_ns": int(sum(render_values) / max(1e-9, sum(record["megapixels"] for record in selected))),
            "effects": {
                effect_id: {"calls": len(values), "total_ns": sum(values), "mean_ns": int(mean(values)), "p95_ns": _percentile(values, 95)}
                for effect_id, values in sorted(effect_groups.items())
            },
        }
    current = {record["fixture_index"]: record for record in records if record["treatment"] == "current"}
    paired: dict[str, Any] = {}
    for treatment in sorted(by_treatment):
        if treatment == "current" or not current:
            continue
        deltas = [
            record["render_only_ns"] - current[record["fixture_index"]]["render_only_ns"]
            for record in records
            if record["treatment"] == treatment and record["fixture_index"] in current
        ]
        paired[treatment] = {"mean_delta_ns": int(mean(deltas)), "p95_delta_ns": _percentile(deltas, 95)}
    slow_render = sorted(records, key=lambda row: row["render_only_ns"], reverse=True)[:10]
    slow_modeled = sorted(records, key=lambda row: row["modeled_production_ns"], reverse=True)[:10]
    compact = lambda row, metric: {
        "fixture_index": row["fixture_index"],
        "treatment": row["treatment"],
        "value_ns": row[metric],
        "recipe_id": row["recipe_id"],
        "object_count": row["object_count"],
        "dimensions": row["dimensions"],
        "rejections": row["rejections"],
        "active_effects": [
            {"id": effect["id"], "duration_ns": effect["duration_ns"], "params": effect["applied_params"]}
            for effect in row["effects"] if effect["applied"]
        ],
    }
    warnings = []
    if samples < 20:
        warnings.append("low_sample_count: use at least 20 measured fixtures before drawing performance conclusions")
    return {
        "treatments": by_treatment,
        "paired_deltas_vs_current": paired,
        "slow_samples": {
            "render_only": [compact(row, "render_only_ns") for row in slow_render],
            "modeled_production": [compact(row, "modeled_production_ns") for row in slow_modeled],
        },
        "warnings": warnings,
    }


def _contact_sheet(records: list[dict[str, Any]], gallery: Path, destination: Path) -> None:
    selected_fixtures = sorted({record["fixture_index"] for record in records})[:3]
    treatment_names = list(dict.fromkeys(record["treatment"] for record in records))
    if not selected_fixtures or not treatment_names:
        return
    thumb = (260, 260)
    pad, label_h = 14, 36
    sheet = Image.new("RGB", (pad + len(treatment_names) * (thumb[0] + pad), pad + len(selected_fixtures) * (thumb[1] + label_h + pad)), "#0b1115")
    draw = ImageDraw.Draw(sheet)
    for row, fixture in enumerate(selected_fixtures):
        for column, treatment in enumerate(treatment_names):
            record = next(item for item in records if item["fixture_index"] == fixture and item["treatment"] == treatment)
            image = Image.open(gallery / record["image"]).convert("RGB")
            image.thumbnail(thumb)
            x = pad + column * (thumb[0] + pad)
            y = pad + row * (thumb[1] + label_h + pad)
            sheet.paste(image, (x, y))
            draw.text((x, y + thumb[1] + 5), f"{fixture:03d} · {treatment}", fill="#e7eef2")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, quality=90)


def _add_difference_images(records: list[dict[str, Any]], gallery: Path) -> None:
    for fixture in sorted({record["fixture_index"] for record in records}):
        current = next(
            (record for record in records if record["fixture_index"] == fixture and record["treatment"] == "current"),
            None,
        )
        if current is None:
            continue
        with Image.open(gallery / current["image"]) as source:
            baseline = source.convert("RGB")
        for record in records:
            if record["fixture_index"] != fixture or record is current:
                continue
            with Image.open(gallery / record["image"]) as source:
                candidate = source.convert("RGB")
            difference = ImageOps.autocontrast(ImageChops.difference(baseline, candidate))
            filename = f"difference-{fixture:03d}--{record['treatment']}.jpg"
            difference.save(gallery / filename, quality=88)
            record["difference_image"] = filename


def _render_report(summary: dict[str, Any], records: list[dict[str, Any]], output: Path) -> None:
    report = output / "report"
    gallery = report / "gallery"
    report.mkdir(parents=True, exist_ok=True)
    treatment_names = list(summary["analysis"]["treatments"])
    fixtures = sorted({record["fixture_index"] for record in records})
    rows: list[str] = []
    for fixture in fixtures:
        fixture_records = {record["treatment"]: record for record in records if record["fixture_index"] == fixture}
        cells = []
        for treatment in treatment_names:
            record = fixture_records.get(treatment)
            if not record:
                continue
            effects = [effect for effect in record["effects"] if effect["applied"]]
            trace = html.escape(json.dumps(effects, indent=2))
            difference = (
                f'<a class="difference" href="gallery/{html.escape(record["difference_image"])}">difference view</a>'
                if record.get("difference_image")
                else ""
            )
            cells.append(
                f'<article><img src="gallery/{html.escape(record["image"])}" alt="fixture {fixture} {html.escape(treatment)}">'
                f'<h3>{html.escape(treatment)}</h3><p>{record["render_only_ns"] / 1e9:.3f} s render · '
                f'{record["modeled_production_ns"] / 1e9:.3f} s modeled</p>{difference}<details><summary>Timing and parameters</summary><pre>{trace}</pre></details></article>'
            )
        rows.append(f'<section class="fixture"><header><strong>fixture-{fixture:03d}</strong><small>{fixture_records[next(iter(fixture_records))]["recipe_id"]}</small></header><div class="cells">{"".join(cells)}</div></section>')
    embedded = json.dumps(summary, sort_keys=True).replace("</", "<\\/")
    warning = summary["study"].get("unsupported_translation")
    warning_text = (
        f'{warning["source"]} is unsupported and mapped to {warning["replacement"]} as an approximation.'
        if warning
        else "Custom appearance matrix; no legacy transform translation is active."
    )
    document = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Augmentation attribution study</title><style>
:root{{--bg:#091014;--panel:#111a20;--ink:#e7eef2;--muted:#9db0bb;--accent:#62d8c6;--warn:#f5b95f}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui}}header.top{{position:sticky;top:0;background:#091014ee;padding:18px 24px;border-bottom:1px solid #23313a;z-index:2}}h1{{margin:0;font-size:24px}}.notice{{margin:20px 24px;padding:12px;border-left:3px solid var(--warn);background:#2a2113}}main{{padding:0 24px 80px}}.fixture{{display:grid;grid-template-columns:150px 1fr;gap:12px;margin:20px 0}}.fixture>header{{background:var(--panel);padding:14px;border-radius:10px;height:max-content}}small{{display:block;color:var(--muted)}}.cells{{display:grid;grid-template-columns:repeat({max(1,len(treatment_names))},minmax(210px,1fr));gap:12px;overflow:auto}}article{{min-width:210px;background:var(--panel);border:1px solid #24333c;border-radius:10px;overflow:hidden}}article img{{width:100%;aspect-ratio:1;object-fit:cover}}article h3,article p,article details,article .difference{{margin:10px 12px}}article h3{{font-size:14px}}article p,summary{{color:var(--muted)}}.difference{{display:inline-block;color:var(--accent)}}pre{{white-space:pre-wrap;font-size:11px;max-height:300px;overflow:auto}}@media(max-width:700px){{.fixture{{grid-template-columns:1fr}}.cells{{grid-template-columns:1fr}}}}
</style></head><body><header class="top"><h1>Heavy augmentation attribution study</h1><small>{html.escape(summary["study"]["family"])} · {summary["study"]["samples"]} measured · {html.escape(summary["environment"]["fingerprint"][:12])}</small></header>
<div class="notice">Paired timing is causal only inside this environment. {html.escape(warning_text)}</div><main>{''.join(rows)}</main><script type="application/json" id="study-summary">{embedded}</script></body></html>"""
    (report / "index.html").write_text(document, encoding="utf-8")


def run_augmentation_study(request: AugmentationStudyRequest, clock: Callable[[], int] = perf_counter_ns) -> dict[str, Any]:
    if request.warmups < 0 or request.samples < 1:
        raise ValueError("warmups must be >= 0 and samples must be >= 1")
    startup_started = clock()
    resolved = load_profile(request.config)
    profile_load_ns = max(0, clock() - startup_started)
    treatments, treatment_metadata = resolve_treatments(
        resolved,
        request.study_definition,
        request.matrix,
        request.include_stress,
    )
    # Validation above intentionally happens before creating a partial report directory.
    output = Path(request.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    gallery = output / "report" / "gallery"
    gallery.mkdir(parents=True, exist_ok=True)
    catalog_started = clock()
    catalog = build_asset_catalog(resolved)
    catalog_ns = max(0, clock() - catalog_started)
    planner = ScenePlanner(resolved, catalog)
    synthesizer = BackgroundSynthesizer(
        catalog,
        resolved.recipes,
        resolved.profile.assets.backgrounds.group_weights,
        resolved.profile.assets.backgrounds.asset_weights,
    )
    renderer_by_treatment = {
        name: SceneRenderer(_profile_with_appearance(resolved, appearance), clock=clock)
        for name, appearance in treatments.items()
    }
    treatment_names = tuple(treatments)
    records: list[dict[str, Any]] = []
    measurements = output / "measurements.jsonl"
    if measurements.exists():
        measurements.unlink()
    total = request.warmups + request.samples
    study_started = clock()
    for fixture_index in range(total):
        plan: ScenePlan | None = None
        background = None
        synthesis_ns = 0
        planning_rejections: list[str] = []
        for candidate_attempt in range(resolved.profile.run.max_candidate_attempts):
            try:
                plan = planner.plan(fixture_index, candidate_attempt)
                synth_started = clock()
                background = synthesizer.synthesize(
                    plan.recipe_id,
                    plan.canvas_size,
                    np.random.default_rng(derive_seed(resolved.profile.run.seed, fixture_index, candidate_attempt, "background-synthesis")),
                )
                synthesis_ns = max(0, clock() - synth_started)
                # Match normal generation semantics: a planned candidate is not a
                # study fixture until the production renderer accepts it. Appearance
                # preserves alpha, so a no-appearance qualification isolates the
                # visibility/placement decision without privileging a treatment.
                renderer_by_treatment["no-appearance" if "no-appearance" in renderer_by_treatment else treatment_names[0]].render(
                    plan, background
                )
                break
            except (SceneRejected, BackgroundSynthesisError) as exc:
                planning_rejections.append(str(exc))
        if plan is None or background is None:
            raise RuntimeError(f"Fixture {fixture_index} exhausted candidate attempts: {planning_rejections}")
        invariant: tuple[str, str, str] | None = None
        for treatment in balanced_treatment_order(treatment_names, fixture_index):
            render_started = clock()
            rendered = renderer_by_treatment[treatment].render(plan, background)
            render_ns = max(0, clock() - render_started)
            signatures = (plan.geometry_signature(), _annotation_signature(rendered), _mask_signature(rendered))
            if invariant is None:
                invariant = signatures
            elif signatures != invariant:
                raise RuntimeError(f"Paired invariant failure for fixture {fixture_index}, treatment {treatment}")
            if fixture_index < request.warmups:
                continue
            measured_index = fixture_index - request.warmups
            payload, encoding_ns = _encode(rendered.image, resolved, clock)
            extension = "jpg" if resolved.profile.output.image_format in {"jpg", "jpeg"} else "png"
            image_name = f"fixture-{measured_index:03d}--{treatment}.{extension}"
            write_started = clock()
            (gallery / image_name).write_bytes(payload)
            writing_ns = max(0, clock() - write_started)
            megapixels = resolved.profile.output.image_size[0] * resolved.profile.output.image_size[1] / 1_000_000.0
            record = {
                "schema_version": 1,
                "fixture_index": measured_index,
                "treatment": treatment,
                "order_index": balanced_treatment_order(treatment_names, fixture_index).index(treatment),
                "geometry_signature": signatures[0],
                "annotation_signature": signatures[1],
                "mask_signature": signatures[2],
                "source_choices": list(background.source_assets),
                "recipe_id": plan.recipe_id,
                "recipe_node_timings_ns": background.node_timings_ns,
                "object_count": len(rendered.annotations),
                "dimensions": list(resolved.profile.output.image_size),
                "megapixels": megapixels,
                "rejections": [*plan.planning_rejections, *rendered.rejected_instances],
                "background_synthesis_ns": synthesis_ns,
                "render_only_ns": render_ns,
                "exclusive_renderer_ns": rendered.exclusive_timings_ns,
                "encoding_ns": encoding_ns,
                "writing_ns": writing_ns,
                "modeled_production_ns": synthesis_ns + render_ns + encoding_ns + writing_ns,
                "effects": list(rendered.effect_traces),
                "image": image_name,
            }
            records.append(record)
            with measurements.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    _add_difference_images(records, gallery)
    measurements.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    analysis = _summarize(records, request.samples)
    environment = {
        "python": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "albumentations": backend_version(),
        "git": _git_identity(Path(__file__).parents[2]),
    }
    environment["fingerprint"] = _sha256_json(environment)
    study = {
        "schema_version": 1,
        "status": "complete",
        "study_id": load_yaml_strict(request.study_definition).get("study_id", output.name),
        "family": resolved.profile.family,
        "config": Path(request.config).name,
        "contract_hash": resolved.contract_hash,
        "catalog_fingerprint": catalog.fingerprint,
        "warmups": request.warmups,
        "samples": request.samples,
        "single_worker": True,
        "balanced_order": True,
        "shared_background_synthesis": True,
        "treatments": {name: appearance.model_dump(mode="json") for name, appearance in treatments.items()},
        "profile_startup_ns": profile_load_ns,
        "catalog_startup_ns": catalog_ns,
        "study_wall_ns": max(0, clock() - study_started),
        **treatment_metadata,
    }
    summary = {"schema_version": 1, "status": "complete", "study": study, "environment": environment, "analysis": analysis}
    (output / "study.json").write_text(json.dumps(study, indent=2), encoding="utf-8")
    report_started = clock()
    _render_report(summary, records, output)
    _contact_sheet(records, gallery, output / "report" / "contact-sheet.jpg")
    study["report_generation_ns"] = max(0, clock() - report_started)
    summary["study"] = study
    # Re-render once with the measured report-generation duration so HTML and
    # summary.json describe the same completed artifact. This second write is
    # intentionally outside the recorded report duration.
    _render_report(summary, records, output)
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "study.json").write_text(json.dumps(study, indent=2), encoding="utf-8")
    return summary


def validate_study_artifacts(output_dir: str | Path) -> dict[str, Any]:
    import re

    root = Path(output_dir)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    html_text = (root / "report" / "index.html").read_text(encoding="utf-8")
    marker = '<script type="application/json" id="study-summary">'
    if marker not in html_text:
        raise ValueError("Report does not embed its summary")
    embedded = html_text.split(marker, 1)[1].split("</script>", 1)[0].replace("<\\/", "</")
    embedded_summary = json.loads(embedded)
    if embedded_summary != summary:
        raise ValueError("HTML and JSON summaries differ")
    links = re.findall(r'(?:src|href)="([^"]+)"', html_text)
    missing = [
        link
        for link in links
        if not link.startswith(("http:", "https:", "#")) and not (root / "report" / link).exists()
    ]
    if missing:
        raise ValueError(f"Report contains missing local links: {missing}")
    return {
        "status": "valid",
        "links": len(links),
        "environment_fingerprint": summary["environment"]["fingerprint"],
    }
