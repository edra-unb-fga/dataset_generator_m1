from __future__ import annotations

import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from .assets import AssetCatalog, build_asset_catalog
from .backgrounds import BackgroundSynthesisError, BackgroundSynthesizer
from .models import ResolvedProfile
from .runstore import RunStore
from .scene import ScenePlanner, SceneRejected, SceneRenderer, derive_seed
from .telemetry import DisplayMode, MetricsAggregator, ResourceSampler, RunReporter, StageTimer


def _disk_preflight(output_dir: Path, resolved: ResolvedProfile) -> dict[str, int]:
    probe = output_dir.resolve()
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    width, height = resolved.profile.output.image_size
    raw_bytes = width * height * 3 * resolved.profile.run.num_images
    encoding_factor = 1.1 if resolved.profile.output.image_format == "png" else 0.6
    estimated_bytes = int(raw_bytes * encoding_factor + resolved.profile.run.num_images * 64 * 1024)
    reserve_bytes = 64 * 1024 * 1024
    free_bytes = int(shutil.disk_usage(probe).free)
    if free_bytes < estimated_bytes + reserve_bytes:
        raise RuntimeError(
            f"Insufficient disk space: estimated {estimated_bytes} bytes plus {reserve_bytes} bytes reserve, "
            f"but only {free_bytes} bytes are free"
        )
    return {"estimated_output_bytes": estimated_bytes, "free_bytes_at_start": free_bytes, "reserve_bytes": reserve_bytes}


@dataclass(frozen=True)
class GenerationOptions:
    display: DisplayMode = "auto"
    output_format: str = "human"
    workers: int | str = 1
    resume: bool = False
    qa_samples: int | None = None
    invocation: tuple[str, ...] = ()


def _annotation_record(annotation: Any) -> dict[str, Any]:
    return {
        "class_id": annotation.class_id,
        "class_name": annotation.class_name,
        "bbox": list(annotation.bbox),
        "normalized_bbox": list(annotation.normalized_bbox),
        "visible_bbox_fraction": annotation.visible_bbox_fraction,
        "source_asset": annotation.source_asset,
        "source_group": annotation.source_group,
        "asset_to_scene": annotation.asset_to_scene.tolist(),
        "asset_to_output": annotation.asset_to_output.tolist(),
    }


def _produce_slot(
    resolved: ResolvedProfile,
    catalog: AssetCatalog,
    slot: int,
    starting_attempt: int,
    coordinator_pid: int,
) -> dict[str, Any]:
    """Render one deterministic slot without performing terminal or pool writes."""
    planner = ScenePlanner(resolved, catalog)
    renderer = SceneRenderer(resolved)
    synthesizer = BackgroundSynthesizer(
        catalog,
        resolved.recipes,
        resolved.profile.assets.backgrounds.group_weights,
        resolved.profile.assets.backgrounds.asset_weights,
    )
    rejections: list[dict[str, Any]] = []
    for candidate_attempt in range(starting_attempt, resolved.profile.run.max_candidate_attempts):
        timings: dict[str, int] = {}
        try:
            with StageTimer(timings, "scene_plan"):
                plan = planner.plan(slot, candidate_attempt)
            with StageTimer(timings, "background_synthesis"):
                background_rng = np.random.default_rng(
                    derive_seed(resolved.profile.run.seed, slot, candidate_attempt, "background-synthesis")
                )
                background = synthesizer.synthesize(plan.recipe_id, plan.canvas_size, background_rng)
            with StageTimer(timings, "scene_render"):
                rendered = renderer.render(plan, background)
            timings.update({f"render.{name}": value for name, value in rendered.exclusive_timings_ns.items()})
            return {
                "accepted": True,
                "image": rendered.image,
                "rejections": rejections,
                "record": {
                    "schema_version": 1,
                    "slot": slot,
                    "candidate_attempt": candidate_attempt,
                    "geometry_signature": plan.geometry_signature(),
                    "intentional_negative": plan.intentional_negative,
                    "attempted_instances": plan.attempted_instances,
                    "camera_rect": list(plan.camera_rect),
                    "scene_to_output": plan.scene_to_output.tolist(),
                    "perspective_quad": plan.perspective_quad.tolist(),
                    "coverage_fraction": rendered.coverage_fraction,
                    "annotations": [_annotation_record(annotation) for annotation in rendered.annotations],
                    "rejected_instances": [*plan.planning_rejections, *rendered.rejected_instances],
                    "background": {
                        "recipe_id": background.recipe_id,
                        "recipe_version": background.recipe_version,
                        "graph_hash": background.graph_hash,
                        "sources": list(background.source_assets),
                        "sampled_parameters": background.sampled_parameters,
                        "node_timings_ns": background.node_timings_ns,
                        "qa": background.qa,
                        "warnings": list(background.warnings),
                    },
                    "stage_timings_ns": timings,
                    "appearance_effects": list(rendered.effect_traces),
                    "execution": {
                        "worker_pid": os.getpid(),
                        "worker_process": os.getpid() != coordinator_pid,
                    },
                },
            }
        except (SceneRejected, BackgroundSynthesisError) as exc:
            rejections.append(
                {
                    "schema_version": 1,
                    "slot": slot,
                    "candidate_attempt": candidate_attempt,
                    "reason": type(exc).__name__,
                    "message": str(exc),
                    "stage_timings_ns": timings,
                }
            )
    return {"accepted": False, "image": None, "record": None, "rejections": rejections}


def generate_pool(resolved: ResolvedProfile, output_dir: str | Path, options: GenerationOptions | None = None) -> dict[str, Any]:
    options = options or GenerationOptions()
    started = perf_counter()
    preflight = _disk_preflight(Path(output_dir), resolved)
    catalog = build_asset_catalog(resolved)
    store = RunStore.open(Path(output_dir), resolved, catalog, resume=options.resume, invocation=options.invocation)
    target = resolved.profile.run.num_images
    workers = int(options.workers)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    metrics = MetricsAggregator(
        target=target,
        configured_recipe_weights=dict(resolved.profile.background_synthesis.recipe_weights),
        configured_foreground_group_weights=dict(resolved.profile.assets.foregrounds.group_weights),
    )
    metrics.set_workload(worker_count=workers, active_workers=0, in_flight=0, queued=target)
    for sample in store.samples:
        metrics.record_sample(sample)
    for rejection in store.rejections:
        metrics.record_rejection(rejection)
    reporter = RunReporter(
        options.display,
        resolved.profile.telemetry.refresh_hz,
        target,
        plain_interval_seconds=resolved.profile.telemetry.plain_interval_seconds,
    )
    resources = ResourceSampler()
    reporter.start(metrics)
    qa_limit = resolved.profile.report.qa_samples if options.qa_samples is None else options.qa_samples
    status = "complete"
    interrupted = False
    fatal_error: str | None = None

    def commit_result(slot: int, result: dict[str, Any]) -> bool:
        nonlocal status, fatal_error
        for rejection in result["rejections"]:
            store.append_rejection(rejection)
            metrics.record_rejection(rejection)
        if not result["accepted"]:
            status = "failed"
            fatal_error = f"Slot {slot} exhausted its candidate-attempt budget"
            return False
        committed = store.commit_sample(result["record"], result["image"], qa=metrics.accepted < qa_limit)
        metrics.record_sample(committed)
        resource = resources.sample_if_due(resolved.profile.telemetry.resource_interval_seconds)
        if resource is not None:
            resource.update({"accepted": metrics.accepted, "candidate_attempts": metrics.candidate_attempts})
            store.append_metric(resource)
            metrics.record_resource(resource)
        reporter.update(metrics)
        if shutil.disk_usage(store.root).free < 32 * 1024 * 1024:
            raise RuntimeError("Generation stopped because remaining disk space fell below 32 MiB")
        if resolved.profile.run.max_wall_seconds and perf_counter() - started > resolved.profile.run.max_wall_seconds:
            raise RuntimeError("Configured maximum wall time exceeded")
        if (
            resolved.profile.run.max_rejection_rate is not None
            and metrics.candidate_attempts >= 10
            and sum(metrics.rejection_reasons.values()) / metrics.candidate_attempts > resolved.profile.run.max_rejection_rate
        ):
            raise RuntimeError("Configured maximum rejection rate exceeded")
        return True

    try:
        completed = store.completed_slots()
        slots = [slot for slot in range(target) if slot not in completed]
        coordinator_pid = os.getpid()
        if workers == 1:
            for slot_index, slot in enumerate(slots):
                metrics.set_workload(worker_count=1, active_workers=1, in_flight=1, queued=max(0, len(slots) - slot_index - 1))
                result = _produce_slot(resolved, catalog, slot, store.next_attempt(slot), coordinator_pid)
                if not commit_result(slot, result):
                    break
        else:
            # Batch windows bound queued jobs and returned-image memory. Sorted commits
            # keep JSONL ordering identical to a single-process generation run.
            window = workers * 2
            executor = ProcessPoolExecutor(max_workers=workers)
            active_futures: dict[Any, int] = {}
            try:
                for offset in range(0, len(slots), window):
                    batch = slots[offset : offset + window]
                    metrics.set_workload(
                        worker_count=workers,
                        active_workers=min(workers, len(batch)),
                        in_flight=len(batch),
                        queued=max(0, len(slots) - offset - len(batch)),
                    )
                    reporter.update(metrics, force=True)
                    active_futures = {
                        executor.submit(
                            _produce_slot,
                            resolved,
                            catalog,
                            slot,
                            store.next_attempt(slot),
                            coordinator_pid,
                        ): slot
                        for slot in batch
                    }
                    results = {active_futures[future]: future.result() for future in as_completed(active_futures)}
                    for slot in sorted(results):
                        if not commit_result(slot, results[slot]):
                            for future in active_futures:
                                future.cancel()
                            break
                    if status == "failed":
                        break
            except KeyboardInterrupt:
                for future in active_futures:
                    future.cancel()
                try:
                    executor.shutdown(wait=True, cancel_futures=True)
                except KeyboardInterrupt:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise SystemExit(130)
                completed_results = {
                    slot: future.result()
                    for future, slot in active_futures.items()
                    if future.done() and not future.cancelled()
                }
                for slot in sorted(completed_results):
                    if slot not in store.completed_slots():
                        commit_result(slot, completed_results[slot])
                interrupted = True
                if status == "complete":
                    status = "interrupted"
            except Exception:
                executor.shutdown(wait=True, cancel_futures=True)
                raise
            else:
                executor.shutdown(wait=True)
    except KeyboardInterrupt:
        interrupted = True
        status = "interrupted"
    except Exception as exc:
        status = "failed"
        fatal_error = f"{type(exc).__name__}: {exc}"
    finally:
        metrics.set_workload(worker_count=workers, active_workers=0, in_flight=0, queued=0)
        final_resource = resources.sample_if_due(resolved.profile.telemetry.resource_interval_seconds, force=True)
        if final_resource is not None:
            final_resource.update({"accepted": metrics.accepted, "candidate_attempts": metrics.candidate_attempts})
            store.append_metric(final_resource)
            metrics.record_resource(final_resource)
        summary = metrics.summary()
        summary.update(
            {
                "schema_version": 1,
                "status": status,
                "interrupted": interrupted,
                "fatal_error": fatal_error,
                "run_id": store.run_id,
                "pool_path": str(store.root),
                "catalog_fingerprint": catalog.fingerprint,
                "contract_hash": resolved.contract_hash,
                "worker_count": workers,
                "preflight": preflight,
                "catalog_quality": {
                    "exact_duplicate_groups": catalog.quality.exact_duplicate_groups,
                    "perceptual_duplicate_groups": catalog.quality.perceptual_duplicate_groups,
                    "background_group_counts": catalog.quality.background_group_counts,
                    "foreground_group_counts": catalog.quality.foreground_group_counts,
                    "class_counts": catalog.quality.class_counts,
                },
            }
        )
        store.write_summary(summary)
        store.write_qa_index()
        reporter.update(metrics, force=True)
        reporter.finish(summary)
    return summary
