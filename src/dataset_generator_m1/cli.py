from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
import psutil

from .config import load_profile
from .catalog import list_profiles, promote_inline_stack, resolved_contract, show_profile
from .augmentation_study import AugmentationStudyRequest, run_augmentation_study
from .exporter import ExportOptions, export_pools, parse_splits
from .generator import GenerationOptions, generate_pool, probe_profile
from .preflight import PreflightRequest, confirm_preflight, run_preflight
from .workflows import benchmark, compare_artifacts, preview_backgrounds, preview_scenes, validate_project


DISPLAY_CHOICES = ["auto", "live", "full", "plain", "quiet"]


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--display", choices=DISPLAY_CHOICES, default="auto")
    parser.add_argument("--output-format", choices=["human", "json"], default="human")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dataset-generator-m1", description="Auditable synthetic dataset generation workbench")
    commands = parser.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser("catalog", help="Discover and inspect reusable configuration profiles")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_list = catalog_commands.add_parser("list", help="List built-in profiles")
    _common(catalog_list)
    catalog_show = catalog_commands.add_parser("show", help="Show one built-in, workspace, or path profile")
    catalog_show.add_argument("reference")
    catalog_show.add_argument("--config")
    _common(catalog_show)
    catalog_promote = catalog_commands.add_parser("promote", help="Promote a composer inline appearance stack")
    catalog_promote.add_argument("--config", required=True)
    catalog_promote.add_argument("--stage", choices=["background", "foreground", "final"], required=True)
    catalog_promote.add_argument("--id", required=True)
    _common(catalog_promote)

    resolve = commands.add_parser("resolve", help="Print the immutable contract resolved from a composer")
    resolve.add_argument("--config", required=True)
    _common(resolve)

    preflight = commands.add_parser("preflight", help="Validate warnings, disk use, and an environment-local ETA")
    preflight.add_argument("--config", required=True)
    preflight.add_argument("--output-dir", required=True)
    preflight.add_argument("--workers", default="1")
    preflight.add_argument("--write-receipt")
    _common(preflight)

    validate = commands.add_parser("validate", help="Validate a profile, assets, recipes, and capabilities")
    validate.add_argument("--config", required=True)
    _common(validate)

    preview = commands.add_parser("preview", help="Build scene or background preview reports")
    preview_commands = preview.add_subparsers(dest="preview_command", required=True)
    preview_scene = preview_commands.add_parser("scenes", help="Compare named scene variants")
    preview_scene.add_argument("--config", required=True)
    preview_scene.add_argument("--variants")
    preview_scene.add_argument("--samples", type=int, default=8)
    preview_scene.add_argument("--output-dir", required=True)
    _common(preview_scene)
    preview_background = preview_commands.add_parser("backgrounds", help="Preview every background recipe")
    preview_background.add_argument("--config", required=True)
    preview_background.add_argument("--samples-per-recipe", type=int, default=4)
    preview_background.add_argument("--output-dir", required=True)
    _common(preview_background)

    generate = commands.add_parser("generate", help="Generate or resume an auditable sample pool")
    generate.add_argument("--config", required=True)
    generate.add_argument("--num-images", type=int)
    generate.add_argument("--output-dir", required=True)
    generate.add_argument("--resume", action="store_true")
    generate.add_argument("--workers", default="1")
    generate.add_argument("--qa-samples", type=int)
    generate.add_argument("--appearance-preset", choices=["realistic-heavy"])
    generate.add_argument("--receipt")
    _common(generate)

    experiment = commands.add_parser("experiment", help="Run controlled experiments")
    experiment_commands = experiment.add_subparsers(dest="experiment_command", required=True)
    augmentations = experiment_commands.add_parser("augmentations", help="Run the paired appearance-attribution study")
    augmentations.add_argument("--config", required=True)
    augmentations.add_argument("--output-dir", required=True)
    augmentations.add_argument("--matrix")
    augmentations.add_argument("--warmups", type=int, default=2)
    augmentations.add_argument("--samples", type=int, default=20)
    augmentations.add_argument("--include-stress", action="store_true")
    _common(augmentations)

    bench = commands.add_parser("benchmark", help="Benchmark fixed scene plans")
    bench.add_argument("--config", required=True)
    bench.add_argument("--output-dir", required=True)
    bench.add_argument("--samples", type=int, default=5)
    bench.add_argument("--warmup", type=int, default=1)
    _common(bench)

    compare = commands.add_parser("compare", help="Compare run or benchmark artifacts")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.add_argument("--output-dir", required=True)
    _common(compare)

    export = commands.add_parser("export", help="Merge generation pools and export YOLO splits")
    export.add_argument("--pool", action="append", required=True)
    export.add_argument("--format", choices=["yolo"], default="yolo")
    export.add_argument("--strategy", choices=["random", "stratified", "asset-disjoint"], default="random")
    export.add_argument("--splits", default="train=0.8,val=0.1,test=0.1")
    export.add_argument("--output-dir", required=True)
    export.add_argument("--preserve-names", action="store_true")
    export.add_argument("--seed", type=int, default=42)
    _common(export)
    return parser


def _workers(value: str, resolved: Any | None = None) -> int:
    if value == "auto":
        cpu_limit = max(1, (os.cpu_count() or 2) - 1)
        if resolved is None:
            return cpu_limit
        width, height = resolved.profile.output.image_size
        canvas_pixels = width * height * resolved.profile.scene.canvas_scale**2
        estimated_bytes_per_worker = max(256 * 1024 * 1024, int(canvas_pixels * 64))
        memory_limit = max(1, int(psutil.virtual_memory().available * 0.60) // estimated_bytes_per_worker)
        return max(1, min(cpu_limit, memory_limit, 32))
    workers = int(value)
    if workers < 1:
        raise ValueError("workers must be auto or an integer >= 1")
    return workers


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "catalog" and args.catalog_command == "list":
        return list_profiles()
    if args.command == "catalog" and args.catalog_command == "show":
        return show_profile(args.reference, composer=args.config)
    if args.command == "catalog" and args.catalog_command == "promote":
        return promote_inline_stack(args.config, args.stage, args.id)
    if args.command == "resolve":
        return resolved_contract(args.config)
    if args.command == "preflight":
        resolved = load_profile(args.config)
        workers = _workers(args.workers, resolved)
        result = run_preflight(
            PreflightRequest(resolved, Path(args.output_dir), workers),
            probe_runner=lambda: probe_profile(resolved),
        )
        if args.write_receipt:
            if args.output_format == "json" or args.display == "quiet":
                raise ValueError("Writing a warning receipt requires an interactive human confirmation")
            required = result["required_acknowledgements"]
            if required and not Confirm.ask(f"Acknowledge {', '.join(required)} for this exact run contract?"):
                raise ValueError("Warning acknowledgement declined")
            result["receipt"] = confirm_preflight(result, args.write_receipt)
        return result
    if args.command == "validate":
        return validate_project(load_profile(args.config))
    if args.command == "preview" and args.preview_command == "backgrounds":
        return preview_backgrounds(load_profile(args.config), args.output_dir, args.samples_per_recipe)
    if args.command == "preview" and args.preview_command == "scenes":
        return preview_scenes(args.config, args.variants, args.output_dir, args.samples)
    if args.command == "generate":
        resolved = load_profile(
            args.config,
            {"num_images": args.num_images, "qa_samples": args.qa_samples, "appearance_preset": args.appearance_preset},
        )
        workers = _workers(args.workers, resolved)
        preflight = run_preflight(
            PreflightRequest(resolved, Path(args.output_dir), workers),
            probe_runner=lambda: probe_profile(resolved),
        )
        receipt_path = Path(args.receipt) if args.receipt else None
        if preflight["required_acknowledgements"] and receipt_path is None and args.output_format != "json" and args.display != "quiet":
            codes = ", ".join(preflight["required_acknowledgements"])
            if not Confirm.ask(f"Acknowledge {codes} for this exact run contract?"):
                raise ValueError("Warning acknowledgement declined")
            receipt_path = Path(".cache") / "preflight-receipts" / f"{preflight['receipt_binding']['hash']}.json"
            confirm_preflight(preflight, receipt_path)
        return generate_pool(
            resolved,
            args.output_dir,
            GenerationOptions(
                display="quiet" if args.output_format == "json" else args.display,
                output_format=args.output_format,
                workers=workers,
                resume=args.resume,
                qa_samples=args.qa_samples,
                invocation=tuple(getattr(args, "_sanitized_invocation", ())),
                preflight_result=preflight,
                receipt_path=receipt_path,
            ),
        )
    if args.command == "experiment" and args.experiment_command == "augmentations":
        return run_augmentation_study(
            AugmentationStudyRequest(
                config=Path(args.config),
                output_dir=Path(args.output_dir),
                matrix=Path(args.matrix) if args.matrix else None,
                warmups=args.warmups,
                samples=args.samples,
                include_stress=args.include_stress,
            )
        )
    if args.command == "benchmark":
        return benchmark(load_profile(args.config), args.output_dir, args.samples, args.warmup)
    if args.command == "compare":
        return compare_artifacts(args.left, args.right, args.output_dir)
    if args.command == "export":
        return export_pools(
            args.pool,
            args.output_dir,
            ExportOptions(args.strategy, parse_splits(args.splits), args.preserve_names, args.seed),
        )
    raise ValueError("Unsupported command")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        raw_invocation = list(sys.argv[1:] if argv is None else argv)
        args._sanitized_invocation = tuple(
            Path(token).name if ("/" in token or "\\" in token) and not token.startswith("--") else token
            for token in raw_invocation
        )
    except SystemExit as exc:
        return int(exc.code)
    try:
        result = _run(args)
        if args.output_format == "json":
            sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
        elif result.get("status") not in {"valid", "complete"}:
            message = result.get("fatal_error") or f"Command ended with status {result.get('status', 'unknown')}"
            Console(stderr=True).print(Panel.fit(str(message), title="[red]generation failed[/red]", border_style="red"))
        elif args.display != "quiet":
            if args.command == "preflight":
                runtime = result["runtime"]
                warning_text = ", ".join(item["code"] for item in result["warnings"]) or "none"
                Console().print(
                    Panel.fit(
                        f"[bold]{result['status']}[/bold]\n"
                        f"ETA: {runtime['lower_seconds']:.1f}–{runtime['upper_seconds']:.1f} s "
                        f"({runtime['confidence']})\n"
                        f"Disk estimate: {result['disk']['estimated_output_bytes']:,} bytes\n"
                        f"Warnings: {warning_text}\n"
                        f"Probe: {'yes' if result['probe']['triggered'] else 'no'}",
                        title="preflight",
                    )
                )
            else:
                Console().print(Panel.fit(f"[bold]{result.get('status', 'complete')}[/bold]", title=args.command))
        return 0 if result.get("status") in {"valid", "complete"} else 1
    except Exception as exc:
        error = {"schema_version": 1, "status": "error", "error_type": type(exc).__name__, "message": str(exc)}
        output_format = getattr(locals().get("args", None), "output_format", "human")
        if output_format == "json":
            sys.stdout.write(json.dumps(error, separators=(",", ":")) + "\n")
        else:
            Console(stderr=True).print(Panel.fit(str(exc), title=f"[red]{type(exc).__name__}[/red]", border_style="red"))
        return 1
