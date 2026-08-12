from __future__ import annotations

import json
import re
import shutil
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

from rich.columns import Columns
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .catalog import list_profiles, resolved_contract, show_profile
from .config import load_profile, load_yaml_strict
from .configurator import (
    APPEARANCE_IDS,
    add_inline_effect,
    default_composer,
    effect_catalog,
    save_composer,
    set_inline_values,
    set_subject_reference,
)
from .execution import resolve_worker_count
from .exporter import ExportOptions, export_pools, parse_splits
from .generator import GenerationOptions, generate_pool, probe_profile
from .inspection import inspect_pool
from .preflight import confirm_preflight
from .preparation import PreparationRequest, prepare_generation


Stage = Literal["readiness", "selection", "essentials", "advanced", "review", "confirm", "running", "results", "cancelled", "done", "preflight"]


@dataclass(frozen=True)
class GuidedSession:
    stage: Stage = "readiness"

    def advance(self, action: str) -> "GuidedSession":
        if action == "cancel":
            return GuidedSession("cancelled")
        transitions: dict[tuple[Stage, str], Stage] = {
            ("readiness", "ready"): "selection",
            ("selection", "select"): "essentials",
            ("essentials", "edit"): "advanced",
            ("advanced", "review"): "review",
            ("review", "prepared"): "confirm",
            ("confirm", "decline"): "cancelled",
            ("confirm", "confirm"): "running",
            ("running", "complete"): "results",
            ("results", "exit"): "done",
            ("running", "back"): "preflight",
            ("advanced", "back"): "essentials",
            ("review", "back"): "advanced",
            ("confirm", "back"): "review",
        }
        target = transitions.get((self.stage, action))
        if target is None:
            raise ValueError(f"Action {action!r} is not valid from guided stage {self.stage!r}")
        return GuidedSession(target)


def choose_live_mode(interactive: bool, width: int, height: int) -> str:
    if not interactive:
        return "plain"
    return "full" if width >= 100 and height >= 30 else "live"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "run"


def suggest_output_dir(root: str | Path, composer_name: str, *, timestamp: str | None = None) -> Path:
    base = Path(root) / "outputs" / "runs" / _slug(composer_name)
    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base / stamp
    suffix = 2
    while candidate.exists():
        candidate = base / f"{stamp}-{suffix:02d}"
        suffix += 1
    return candidate


def discover_composers(root: str | Path = ".") -> dict[str, list[dict[str, Any]]]:
    root = Path(root).resolve()
    result: dict[str, list[dict[str, Any]]] = {"managed": [], "examples": [], "invalid": []}
    groups = (("managed", root / "configs"), ("examples", root / "examples" / "configs"))
    for kind, directory in groups:
        for path in sorted(directory.glob("*.yaml")):
            try:
                resolved = load_profile(path)
            except Exception as exc:
                if kind == "managed":
                    result["invalid"].append({"name": path.stem, "path": path, "error": str(exc)})
                continue
            result[kind].append(
                {
                    "name": path.stem,
                    "path": path,
                    "family": resolved.profile.family,
                    "contract_hash": resolved.contract_hash,
                }
            )
    return result


def discover_incomplete_runs(root: str | Path = ".") -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for control_path in sorted((Path(root) / "outputs" / "runs").glob("**/control.json"), reverse=True):
        try:
            control = json.loads(control_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if control.get("actual_state") in {"running", "draining", "paused", "stopping", "interrupted", "failed"}:
            runs.append({"path": control_path.parent, "state": control.get("actual_state")})
    return runs[:10]


def profile_help(reference: str, composer: str | Path | None = None) -> str:
    details = show_profile(reference, composer=composer)
    metadata = details["metadata"]
    header = (
        f"**Profile:** `{metadata.get('id', reference)}`  \n"
        f"**Status:** {metadata.get('status', 'local')}  \n"
        f"**Performance risk:** {metadata.get('performance_risk', 'unknown')}  \n"
        f"**Evidence:** {', '.join(metadata.get('evidence', [])) or 'none recorded'}\n\n"
    )
    documentation = details.get("documentation")
    if documentation:
        return header + str(documentation)
    return header + "No tracked README is available."


def _terminal_height(console: Console) -> int:
    return int(getattr(console.size, "height", 24))


def _readiness(console: Console, root: Path) -> None:
    incomplete = discover_incomplete_runs(root)
    table = Table(title="Environment and run readiness", expand=True)
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Managed composers", str(len(discover_composers(root)["managed"])))
    table.add_row("Incomplete runs", str(len(incomplete)))
    table.add_row("Interactive controls", "available" if sys.stdin.isatty() else "external commands only")
    console.print(table)
    if incomplete:
        console.print(Panel("\n".join(f"{item['state']}: {item['path']}" for item in incomplete), title="Recent resumable/incomplete runs"))


def _copy_example(path: Path, root: Path) -> Path:
    destination = root / "configs" / path.name
    suffix = 2
    while destination.exists():
        destination = root / "configs" / f"{path.stem}-{suffix:02d}{path.suffix}"
        suffix += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    load_profile(destination)
    return destination


def _select_config(root: Path, provided: str | Path | None, console: Console, ask: Callable[..., str]) -> Path:
    if provided:
        path = Path(provided).resolve()
        load_profile(path)
        return path
    discovery = discover_composers(root)
    choices = [*discovery["managed"], *discovery["examples"]]
    if not choices:
        family = ask("No composers found. Create family", choices=["landing", "manometro"], default="landing")
        path = root / "configs" / f"{family}.yaml"
        return save_composer(default_composer(family), path)
    table = Table(title="Saved composers and shipped examples", expand=True)
    table.add_column("#")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Family")
    for index, item in enumerate(choices, 1):
        table.add_row(str(index), "saved" if item in discovery["managed"] else "example", item["name"], item["family"])
    console.print(table)
    if discovery["invalid"]:
        console.print(Panel("\n".join(f"{item['name']}: {item['error']}" for item in discovery["invalid"]), title="Invalid managed files", border_style="yellow"))
    selected = int(ask("Composer number", default="1")) - 1
    if selected not in range(len(choices)):
        raise ValueError("Composer selection is out of range")
    item = choices[selected]
    return item["path"]


def _appearance_id(resolved: Any) -> str:
    return next((item["id"] for item in resolved.profile_metadata if item.get("subject") == "appearance"), "inline/local")


def _essentials_panel(config: Path, output_dir: Path) -> Panel:
    resolved = load_profile(config)
    profile = resolved.profile
    text = (
        f"Family: [bold]{profile.family}[/bold]\n"
        f"Images: {profile.run.num_images}\n"
        f"Appearance: {_appearance_id(resolved)}\n"
        f"Dimensions: {profile.output.image_size[0]} × {profile.output.image_size[1]}\n"
        f"Workers: {resolve_worker_count(None, resolved)}\n"
        f"Destination: {output_dir}\n"
        "Warnings, disk use, and Estimated time remaining: calculated during full preflight"
    )
    return Panel(text, title="Run essentials", border_style="cyan")


def _edit_composer(config: Path, output_dir: Path, console: Console, ask: Callable[..., str], confirm: Callable[..., bool]) -> tuple[Path, Path]:
    document = load_yaml_strict(config)
    resolved = load_profile(config)
    console.print(_essentials_panel(config, output_dir))
    if confirm("Edit essentials?", default=False):
        document = set_inline_values(
            document,
            "run",
            {
                "num_images": int(ask("Number of images", default=str(resolved.profile.run.num_images))),
                "seed": int(ask("Seed", default=str(resolved.profile.run.seed))),
            },
        )
        workers = ask("Workers (auto or integer)", default=str(resolved.profile.execution.workers))
        document = set_inline_values(document, "execution", {"workers": workers if workers == "auto" else int(workers)})
        width = int(ask("Width", default=str(resolved.profile.output.image_size[0])))
        height = int(ask("Height", default=str(resolved.profile.output.image_size[1])))
        document = set_inline_values(document, "output", {"image_size": [width, height]})
        destination = ask("Run destination", default=str(output_dir))
        output_dir = Path(destination)
    if confirm("Open Advanced settings?", default=False):
        document = _advanced_editor(document, config, console, ask)
    save_composer(document, config)
    return config, output_dir


def _advanced_editor(document: dict[str, Any], config: Path, console: Console, ask: Callable[..., str]) -> dict[str, Any]:
    while True:
        action = ask("Advanced: appearance, subject, effect, help, or done", choices=["appearance", "subject", "effect", "help", "done"], default="done")
        if action == "done":
            return document
        if action == "appearance":
            for index, reference in enumerate(APPEARANCE_IDS, 1):
                console.print(f"{index}. {reference}")
            selected = int(ask("Appearance number", default="1")) - 1
            if selected not in range(len(APPEARANCE_IDS)):
                raise ValueError("Appearance selection is out of range")
            document.setdefault("appearance", {})["preset"] = APPEARANCE_IDS[selected]
            console.print(Markdown(profile_help(APPEARANCE_IDS[selected], config)))
        elif action == "help":
            reference = ask("Profile ID", default="builtin:appearance/realistic-heavy")
            console.print(Markdown(profile_help(reference, config)))
        elif action == "subject":
            subjects = ["run", "assets", "output", "sampling", "scene", "background_recipes", "background_mixing", "execution", "telemetry", "reporting"]
            subject = ask("Subject", choices=subjects, default="sampling")
            profiles = [item for item in list_profiles(config)["profiles"] if item["subject"] == subject]
            console.print("\n".join(item["id"] for item in profiles) or "No catalog entries")
            reference = ask("Profile ID or YAML path", default=str(document[subject]))
            console.print(Markdown(profile_help(reference, config)))
            document = set_subject_reference(document, subject, reference)
        elif action == "effect":
            docs = effect_catalog()["effects"]
            stage = ask("Stage", choices=["background", "foreground", "final"], default="final")
            available = [name for name in sorted(docs) if stage in docs[name]["stages"]]
            for index, name in enumerate(available, 1):
                console.print(f"{index}. {name}: {docs[name]['summary']}")
            effect_type = available[int(ask("Effect number", default="1")) - 1]
            documentation = docs[effect_type].get("documentation", effect_catalog()["documentation"])
            console.print(Panel(f"{docs[effect_type]['summary']}\nDocumentation: {documentation}", title=effect_type))
            document = add_inline_effect(
                document,
                stage=stage,
                effect_type=effect_type,
                effect_id=ask("Stable effect ID", default=f"custom-{stage}-{effect_type.lower()}"),
                probability=float(ask("Probability", default="1.0")),
                params=json.loads(ask("Parameters as JSON", default="{}")),
            )


def _review_panel(config: Path, output_dir: Path) -> Group:
    resolved = load_profile(config)
    contract = resolved_contract(config)
    references = Table(title="Resolved contract", expand=True)
    references.add_column("Subject")
    references.add_column("Reference")
    for subject, node in resolved.reference_graph.items():
        if subject == "appearance":
            choice = node.get("preset", {}).get("reference", "inline/local")
        else:
            choice = node.get("reference", "inline")
        references.add_row(subject, str(choice))
    return Group(_essentials_panel(config, output_dir), references, Panel(contract["contract_hash"], title="Immutable contract hash"))


def _preflight_panel(preflight: dict[str, Any]) -> Panel:
    runtime = preflight["runtime"]
    warnings = "\n".join(f"• {item['code']} ({item['severity']})" for item in preflight["warnings"]) or "none"
    return Panel(
        f"Estimated time remaining: {runtime['lower_seconds']:.1f}–{runtime['upper_seconds']:.1f}s ({runtime['confidence']})\n"
        f"Disk estimate: {preflight['disk']['estimated_output_bytes']:,} bytes\nWarnings:\n{warnings}",
        title="Full preflight",
        border_style="yellow" if preflight["warnings"] else "green",
    )


def render_results_dashboard(summary: dict[str, Any], inspection: dict[str, Any]) -> Group:
    output = Path(summary["pool_path"])
    quality = Panel(
        f"Inspection: {inspection['status']}\nQA gallery: {output / 'qa' / 'index.html'}\nFindings: {len(inspection['findings'])}",
        title="Quality and QA",
    )
    performance = Panel(
        f"Active time: {summary['elapsed_seconds']:.2f}s\nPaused: {summary['paused_seconds']:.2f}s\n"
        f"Throughput: {summary['throughput_images_per_second']:.2f} images/s\nObservation: {summary.get('performance_observation', {}).get('status', 'unknown')}",
        title="Performance",
    )
    audit = Panel(
        f"Pool: {output}\nManifest: {output / 'run.json'}\nSummary: {output / 'summary.json'}\nControl log: {output / 'control-events.jsonl'}",
        title="Audit evidence",
    )
    return Group(Panel(f"{summary['status']} — {summary['accepted_samples']}/{summary['target_samples']} samples", title="Run results"), Columns([quality, performance], expand=True), audit)


def _non_tty_message(config: str | Path | None) -> str:
    chosen = str(config or "examples/configs/landing_minimal.yaml")
    return (
        "`start` is interactive-only and no terminal was detected. Use the atomic commands instead:\n"
        f"  configure --family landing --output configs/my-landing.yaml\n"
        f"  resolve --config {chosen}\n"
        f"  preflight --config {chosen} --output-dir outputs/runs/my-run\n"
        f"  generate --config {chosen} --output-dir outputs/runs/my-run"
    )


def run_guided_start(
    config: str | Path | None = None,
    *,
    root: str | Path = ".",
    console: Console | None = None,
    ask: Callable[..., str] = Prompt.ask,
    confirm: Callable[..., bool] = Confirm.ask,
) -> dict[str, Any]:
    console = console or Console()
    if not (console.is_interactive and sys.stdin.isatty()):
        raise RuntimeError(_non_tty_message(config))
    root = Path(root).resolve()
    session = GuidedSession()
    _readiness(console, root)
    session = session.advance("ready")
    provided = config
    while True:
        chosen = _select_config(root, provided, console, ask)
        selection_action = ask("Continue with this composer?", choices=["continue", "back", "cancel"], default="continue")
        if selection_action == "cancel":
            return {"schema_version": 1, "status": "cancelled", "stage": "selection"}
        if selection_action == "back":
            provided = None
            _readiness(console, root)
            continue
        break
    if root / "examples" / "configs" in chosen.parents:
        chosen = _copy_example(chosen, root)
        console.print(f"Copied shipped example to managed composer: [bold]{chosen}[/bold]")
    session = session.advance("select")
    output_dir = suggest_output_dir(root, chosen.stem)
    while True:
        chosen, output_dir = _edit_composer(chosen, output_dir, console, ask, confirm)
        session = session.advance("edit") if session.stage == "essentials" else GuidedSession("advanced")
        session = session.advance("review")
        console.print(_review_panel(chosen, output_dir))
        review_action = ask("Prepare this run?", choices=["prepare", "back", "cancel"], default="prepare")
        if review_action == "cancel":
            return {"schema_version": 1, "status": "cancelled", "stage": "review"}
        if review_action == "back":
            session = session.advance("back")
            continue
        break
    resolved = load_profile(chosen)
    workers = resolve_worker_count(None, resolved)
    prepared = prepare_generation(
        PreparationRequest(resolved, output_dir, workers),
        probe_runner=lambda: probe_profile(resolved),
    )
    console.print(_preflight_panel(prepared.preflight))
    session = session.advance("prepared")
    receipt_path: Path | None = None
    required = prepared.preflight["required_acknowledgements"]
    if required:
        if not confirm(f"Acknowledge {', '.join(required)} for this exact run?", default=False):
            return {"schema_version": 1, "status": "cancelled", "stage": "warning-acknowledgement"}
        receipt_path = root / ".cache" / "preflight-receipts" / f"{prepared.preflight['receipt_binding']['hash']}.json"
        confirm_preflight(prepared.preflight, receipt_path)
    if not confirm("Start generation with this exact prepared contract?", default=False):
        return {"schema_version": 1, "status": "cancelled", "stage": "final-confirmation"}
    session = session.advance("confirm")
    display = choose_live_mode(True, console.width, _terminal_height(console))
    summary = generate_pool(
        resolved,
        output_dir,
        GenerationOptions(
            display=display,
            workers=workers,
            prepared=prepared,
            receipt_path=receipt_path,
            invocation=("start", "--config", chosen.name),
        ),
    )
    session = session.advance("complete")
    inspection = inspect_pool(output_dir)
    console.print(render_results_dashboard(summary, inspection))
    actions = ["qa", "inspect", "export-detection", "export-segmentation", "another", "exit"]
    if summary["status"] in {"interrupted", "failed"}:
        actions.insert(3, "resume")
    while True:
        action = ask("Next action", choices=actions, default="exit")
        if action == "qa":
            webbrowser.open((output_dir / "qa" / "index.html").resolve().as_uri())
        elif action == "inspect":
            inspection = inspect_pool(output_dir)
            console.print(render_results_dashboard(summary, inspection))
        elif action in {"export-detection", "export-segmentation"}:
            task = action.removeprefix("export-")
            destination = output_dir.with_name(output_dir.name + f"-yolo-{task}")
            export_pools(
                [output_dir],
                destination,
                ExportOptions(
                    strategy="random",
                    splits=parse_splits("train=0.8,val=0.1,test=0.1"),
                    preserve_names=False,
                    seed=42,
                    task=task,
                    mask_semantics="family",
                ),
            )
            console.print(Panel(str(destination), title=f"YOLO {task} export"))
        elif action == "resume":
            summary = generate_pool(
                resolved,
                output_dir,
                GenerationOptions(display=display, workers=workers, prepared=prepared, receipt_path=receipt_path, resume=True),
            )
            inspection = inspect_pool(output_dir)
            console.print(render_results_dashboard(summary, inspection))
        elif action == "another":
            return run_guided_start(root=root, console=console, ask=ask, confirm=confirm)
        else:
            session = session.advance("exit")
            return {"schema_version": 1, "status": "complete", "stage": session.stage, "summary": summary, "inspection": inspection, "config": str(chosen)}
