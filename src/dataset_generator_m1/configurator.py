from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .catalog import list_profiles, show_profile
from .config import load_profile
from .filters import SUPPORTED_TRANSFORMS, validate_transform_specs
from .execution import resolve_worker_count
from .models import GenerationComposer, TransformSpec
from .preflight import PreflightRequest, run_preflight


APPEARANCE_IDS = (
    "builtin:appearance/realistic-heavy",
    "builtin:appearance/current-fast",
    "builtin:appearance/legacy-heavy-compatible",
    "builtin:appearance/random-fog-heavy",
    "builtin:appearance/no-appearance",
    "builtin:appearance/all-effects-stress",
)


def _composer_payload(document: dict[str, Any] | GenerationComposer) -> dict[str, Any]:
    model = document if isinstance(document, GenerationComposer) else GenerationComposer.model_validate(document)
    payload = model.model_dump(mode="json", exclude_none=True)
    appearance = payload["appearance"]
    for key in ("background", "foreground", "final"):
        if not appearance.get(key):
            appearance.pop(key, None)
    appearance_inline = appearance.get("inline", {})
    for key in ("background", "foreground", "final"):
        if not appearance_inline.get(key):
            appearance_inline.pop(key, None)
    if not appearance_inline:
        appearance.pop("inline", None)
    inline = payload.get("inline", {})
    for key in list(inline):
        if not inline[key]:
            inline.pop(key)
    if not inline:
        payload.pop("inline", None)
    return payload


def effect_catalog() -> dict[str, Any]:
    path = Path(__file__).with_name("knowledge") / "effects.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    documented = set(payload["effects"])
    if documented != SUPPORTED_TRANSFORMS:
        missing = sorted(SUPPORTED_TRANSFORMS - documented)
        stale = sorted(documented - SUPPORTED_TRANSFORMS)
        raise ValueError(f"Effect documentation drift; missing={missing}, stale={stale}")
    return payload


def default_composer(family: str, *, appearance: str = APPEARANCE_IDS[0]) -> dict[str, Any]:
    if family not in {"landing", "manometro"}:
        raise ValueError("family must be landing or manometro")
    raw = {
        "schema_version": 2,
        "family": f"builtin:family/{family}",
        "run": f"builtin:run/{family}-standard",
        "assets": f"builtin:assets/{family}",
        "output": "builtin:output/standard",
        "sampling": f"builtin:sampling/{family}-standard",
        "scene": "builtin:scene/standard",
        "background_recipes": "builtin:background_recipes/standard",
        "background_mixing": "builtin:background_mixing/standard",
        "appearance": {"preset": appearance},
        "execution": "builtin:execution/standard",
        "telemetry": "builtin:telemetry/standard",
        "reporting": "builtin:reporting/standard",
        "inline": {},
    }
    return _composer_payload(raw)


def save_composer(document: dict[str, Any], destination: str | Path) -> Path:
    validated = _composer_payload(document)
    path = Path(destination).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(yaml.safe_dump(validated, sort_keys=False), encoding="utf-8")
    os.replace(temporary, path)
    load_profile(path)
    return path


def set_inline_values(document: dict[str, Any], subject: str, values: dict[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(document)
    inline = candidate.setdefault("inline", {})
    existing = inline.setdefault(subject, {})
    existing.update(values)
    return _composer_payload(candidate)


def set_subject_reference(document: dict[str, Any], subject: str, reference: str) -> dict[str, Any]:
    if subject not in {
        "run",
        "assets",
        "output",
        "sampling",
        "scene",
        "background_recipes",
        "background_mixing",
        "execution",
        "telemetry",
        "reporting",
    }:
        raise ValueError(f"Subject reference is not user-selectable here: {subject}")
    candidate = deepcopy(document)
    candidate[subject] = reference
    return _composer_payload(candidate)


def add_inline_effect(
    document: dict[str, Any],
    *,
    stage: str,
    effect_type: str,
    effect_id: str,
    probability: float,
    params: dict[str, Any],
) -> dict[str, Any]:
    docs = effect_catalog()["effects"]
    if effect_type not in docs or stage not in docs[effect_type]["stages"]:
        raise ValueError(f"{effect_type} is not documented for {stage}")
    spec = TransformSpec(id=effect_id, type=effect_type, probability=probability, params=params)
    candidate = deepcopy(document)
    appearance = candidate.setdefault("appearance", {})
    inline = appearance.setdefault("inline", {})
    stack = inline.setdefault(stage, [])
    stack.append(spec.model_dump(mode="json"))
    validate_transform_specs(tuple(TransformSpec.model_validate(item) for item in stack), f"appearance.{stage}")
    return _composer_payload(candidate)


def configuration_summary(config: str | Path, output_dir: str | Path) -> dict[str, Any]:
    resolved = load_profile(config)
    worker_count = resolve_worker_count(None, resolved)
    preflight = run_preflight(PreflightRequest(resolved, Path(output_dir), worker_count))
    return {
        "schema_version": 1,
        "status": "complete",
        "config": Path(config).resolve().as_posix(),
        "contract_hash": resolved.contract_hash,
        "family": resolved.profile.family,
        "appearance": next(
            (item["id"] for item in resolved.profile_metadata if item.get("subject") == "appearance"),
            "inline/local",
        ),
        "subjects": resolved.reference_graph,
        "warnings": preflight["warnings"],
        "runtime": preflight["runtime"],
        "disk": preflight["disk"],
        "suggested_next": f"preflight --config {Path(config).name} --output-dir {Path(output_dir).as_posix()}",
    }


def _render_cockpit(console: Console, config: Path, output_dir: Path) -> dict[str, Any]:
    summary = configuration_summary(config, output_dir)
    resolved = load_profile(config)
    table = Table(title="Configuration cockpit", expand=True)
    table.add_column("Subject")
    table.add_column("Choice")
    for subject, node in resolved.reference_graph.items():
        if subject == "appearance":
            choice = node["preset"]["reference"]
        else:
            choice = node["reference"]
        table.add_row(subject, choice)
    warnings = ", ".join(item["code"] for item in summary["warnings"]) or "none"
    runtime = summary["runtime"]
    console.print(table)
    console.print(
        Panel.fit(
            f"Warnings: {warnings}\nETA: {runtime['lower_seconds']:.1f}–{runtime['upper_seconds']:.1f}s ({runtime['confidence']})\n"
            f"Next: {summary['suggested_next']}",
            title="Preflight snapshot",
        )
    )
    return summary


def configure_interactive(
    *,
    family: str,
    destination: str | Path,
    output_dir: str | Path,
    appearance: str = APPEARANCE_IDS[0],
    console: Console | None = None,
    ask: Callable[..., str] = Prompt.ask,
) -> dict[str, Any]:
    console = console or Console()
    document = default_composer(family, appearance=appearance)
    path = save_composer(document, destination)
    output = Path(output_dir)
    while True:
        summary = _render_cockpit(console, path, output)
        choice = ask(
            "Choose: s=subject, a=appearance, e=add effect, r=run, o=output, f=finish",
            choices=["s", "a", "e", "r", "o", "f"],
            default="f",
        )
        if choice == "f":
            return summary
        if choice == "s":
            subjects = [
                "run",
                "assets",
                "output",
                "sampling",
                "scene",
                "background_recipes",
                "background_mixing",
                "execution",
                "telemetry",
                "reporting",
            ]
            subject = ask("Subject", choices=subjects, default="sampling")
            available = [item for item in list_profiles(path)["profiles"] if item["subject"] == subject]
            for item in available:
                console.print(f"- {item['id']} — {item['status']} / {item['performance_risk']}")
            reference = ask("Profile ID or YAML path", default=document[subject])
            details = show_profile(reference, composer=path)
            if details["documentation"]:
                console.print(Panel.fit(details["documentation"], title=reference))
            document = set_subject_reference(document, subject, reference)
        elif choice == "a":
            for index, reference in enumerate(APPEARANCE_IDS, start=1):
                details = show_profile(reference)
                console.print(f"{index}. {reference} — {details['metadata']['status']} / {details['metadata']['performance_risk']}")
            selected = int(ask("Profile number", default="1")) - 1
            if selected not in range(len(APPEARANCE_IDS)):
                raise ValueError("Appearance profile number is out of range")
            document["appearance"]["preset"] = APPEARANCE_IDS[selected]
        elif choice == "e":
            docs = effect_catalog()["effects"]
            stage = ask("Stage", choices=["background", "foreground", "final"], default="final")
            available = [name for name in sorted(docs) if stage in docs[name]["stages"]]
            for index, name in enumerate(available, start=1):
                console.print(f"{index}. {name}: {docs[name]['summary']}")
            selected = int(ask("Effect number", default="1")) - 1
            if selected not in range(len(available)):
                raise ValueError("Effect number is out of range")
            effect_type = available[selected]
            console.print(f"Documentation: {docs[effect_type].get('documentation', effect_catalog()['documentation'])}")
            probability = float(ask("Probability", default="1.0"))
            effect_id = ask("Stable effect ID", default=f"custom-{stage}-{effect_type.lower()}")
            params = json.loads(ask("Parameters as JSON", default="{}"))
            document = add_inline_effect(
                document,
                stage=stage,
                effect_type=effect_type,
                effect_id=effect_id,
                probability=probability,
                params=params,
            )
        elif choice == "r":
            document = set_inline_values(
                document,
                "run",
                {
                    "num_images": int(ask("Number of images", default="50")),
                    "seed": int(ask("Seed", default="42")),
                },
            )
            document = set_inline_values(document, "execution", {"workers": ask("Workers (auto or integer)", default="1")})
            workers = document["inline"]["execution"]["workers"]
            if isinstance(workers, str) and workers != "auto":
                document["inline"]["execution"]["workers"] = int(workers)
        elif choice == "o":
            width = int(ask("Width", default="1280"))
            height = int(ask("Height", default="1280"))
            image_format = ask("Format", choices=["jpg", "png"], default="jpg")
            document = set_inline_values(document, "output", {"image_size": [width, height], "image_format": image_format})
        path = save_composer(document, path)


def configure_noninteractive(
    *, family: str, destination: str | Path, output_dir: str | Path, appearance: str = APPEARANCE_IDS[0]
) -> dict[str, Any]:
    path = save_composer(default_composer(family, appearance=appearance), destination)
    return configuration_summary(path, output_dir)
