from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from statistics import mean, median
from time import perf_counter, perf_counter_ns
from typing import Any, Callable, Literal

import psutil
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


DisplayMode = Literal["auto", "live", "full", "plain", "quiet"]


class StageTimer(AbstractContextManager["StageTimer"]):
    def __init__(self, timings: dict[str, int], stage: str, clock: Callable[[], int] = perf_counter_ns) -> None:
        self.timings = timings
        self.stage = stage
        self.clock = clock
        self.started = 0

    def __enter__(self) -> "StageTimer":
        self.started = self.clock()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.timings[self.stage] = self.timings.get(self.stage, 0) + self.clock() - self.started


@dataclass
class MetricsAggregator:
    target: int
    configured_recipe_weights: dict[str, float] = field(default_factory=dict)
    configured_foreground_group_weights: dict[str, float] = field(default_factory=dict)
    clock: Callable[[], float] = field(default=perf_counter, repr=False)
    started_at: float = field(init=False)
    paused_total_seconds: float = 0.0
    pause_started_at: float | None = None
    baseline_accepted: int = 0
    baseline_candidate_attempts: int = 0
    measurement_active: bool = False
    accepted: int = 0
    candidate_attempts: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    stage_timings: dict[str, list[int]] = field(default_factory=dict)
    session_stage_timings: dict[str, list[int]] = field(default_factory=dict)
    class_counts: dict[str, int] = field(default_factory=dict)
    recipe_counts: dict[str, int] = field(default_factory=dict)
    foreground_group_counts: dict[str, int] = field(default_factory=dict)
    negative_count: int = 0
    mask_archive_bytes: int = 0
    segmentation_ious: list[float] = field(default_factory=list)
    segmentation_area_errors: list[float] = field(default_factory=list)
    segmentation_warning_instances: int = 0
    object_attempts: int = 0
    object_rejections: int = 0
    background_warnings: dict[str, int] = field(default_factory=dict)
    background_qa: dict[str, list[float]] = field(default_factory=dict)
    rejection_costs: dict[str, int] = field(default_factory=dict)
    resource_peaks: dict[str, float] = field(default_factory=dict)
    worker_count: int = 1
    active_workers: int = 0
    in_flight: int = 0
    queued: int = 0
    run_state: str = "running"

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    def record_sample(self, record: dict[str, Any]) -> None:
        self.accepted += 1
        self.candidate_attempts += 1
        for stage, duration in record.get("stage_timings_ns", {}).items():
            self.stage_timings.setdefault(stage, []).append(int(duration))
            if self.measurement_active:
                self.session_stage_timings.setdefault(stage, []).append(int(duration))
        for annotation in record.get("annotations", []):
            name = str(annotation["class_name"])
            self.class_counts[name] = self.class_counts.get(name, 0) + 1
            group = str(annotation.get("source_group", "unknown"))
            self.foreground_group_counts[group] = self.foreground_group_counts.get(group, 0) + 1
        self.object_attempts += int(record.get("attempted_instances", len(record.get("annotations", []))))
        self.object_rejections += len(record.get("rejected_instances", []))
        background = record.get("background", {})
        recipe = str(background.get("recipe_id", "unknown"))
        self.recipe_counts[recipe] = self.recipe_counts.get(recipe, 0) + 1
        for node, duration in background.get("node_timings_ns", {}).items():
            self.stage_timings.setdefault(f"background.node.{node}", []).append(int(duration))
            if self.measurement_active:
                self.session_stage_timings.setdefault(f"background.node.{node}", []).append(int(duration))
        for key, value in background.get("qa", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.background_qa.setdefault(str(key), []).append(float(value))
        for warning in background.get("warnings", []):
            self.background_warnings[str(warning)] = self.background_warnings.get(str(warning), 0) + 1
        if record.get("intentional_negative"):
            self.negative_count += 1
        self.mask_archive_bytes += int(record.get("mask_evidence", {}).get("byte_count", 0))
        quality = record.get("segmentation_quality", {})
        self.segmentation_warning_instances += int(quality.get("warning_instances", 0))
        for instance in quality.get("instances", []):
            for result in instance.get("semantics", {}).values():
                self.segmentation_ious.append(float(result.get("iou", 0.0)))
                self.segmentation_area_errors.append(float(result.get("area_error", 1.0)))

    def record_rejection(self, record: dict[str, Any]) -> None:
        self.candidate_attempts += 1
        reason = str(record.get("reason", "unknown"))
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
        self.rejection_costs[reason] = self.rejection_costs.get(reason, 0) + sum(
            int(duration) for duration in record.get("stage_timings_ns", {}).values()
        )
        for stage, duration in record.get("stage_timings_ns", {}).items():
            self.stage_timings.setdefault(stage, []).append(int(duration))
            if self.measurement_active:
                self.session_stage_timings.setdefault(stage, []).append(int(duration))

    def record_resource(self, record: dict[str, Any]) -> None:
        for key in ("cpu_percent", "rss_bytes", "read_bytes", "write_bytes"):
            value = float(record.get(key, 0.0))
            self.resource_peaks[key] = max(self.resource_peaks.get(key, 0.0), value)

    def set_workload(self, *, worker_count: int, active_workers: int, in_flight: int, queued: int) -> None:
        self.worker_count = worker_count
        self.active_workers = active_workers
        self.in_flight = in_flight
        self.queued = queued

    def set_run_state(self, state: str) -> None:
        self.run_state = state

    @property
    def wall_elapsed_seconds(self) -> float:
        return max(0.0, self.clock() - self.started_at)

    @property
    def paused_seconds(self) -> float:
        active_pause = self.clock() - self.pause_started_at if self.pause_started_at is not None else 0.0
        return max(0.0, self.paused_total_seconds + active_pause)

    @property
    def active_elapsed_seconds(self) -> float:
        return max(1e-9, self.wall_elapsed_seconds - self.paused_seconds)

    @property
    def elapsed_seconds(self) -> float:
        return self.active_elapsed_seconds

    def begin_pause(self) -> None:
        if self.pause_started_at is None:
            self.pause_started_at = self.clock()

    def end_pause(self) -> None:
        if self.pause_started_at is not None:
            self.paused_total_seconds += self.clock() - self.pause_started_at
            self.pause_started_at = None

    def begin_live_measurement(self) -> None:
        """Start a fresh ETA window after replaying samples from an earlier session."""
        self.started_at = self.clock()
        self.paused_total_seconds = 0.0
        self.pause_started_at = None
        self.baseline_accepted = self.accepted
        self.baseline_candidate_attempts = self.candidate_attempts
        self.session_stage_timings = {}
        self.measurement_active = True

    @property
    def throughput(self) -> float:
        return max(0, self.accepted - self.baseline_accepted) / self.elapsed_seconds

    @property
    def eta_seconds(self) -> float:
        remaining = max(0, self.target - self.accepted)
        return remaining / self.throughput if self.throughput > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        def summarize_stages(source: dict[str, list[int]]) -> dict[str, dict[str, float | int]]:
            result: dict[str, dict[str, float | int]] = {}
            for stage, values in source.items():
                ordered = sorted(values)

                def percentile(fraction: float) -> int:
                    if not ordered:
                        return 0
                    return int(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))])

                result[stage] = {
                    "count": len(values),
                    "total_ns": int(sum(values)),
                    "mean_ns": int(mean(values)),
                    "median_ns": int(median(values)),
                    "p90_ns": percentile(0.90),
                    "p95_ns": percentile(0.95),
                    "p99_ns": percentile(0.99),
                }
            return result

        stage_summary = summarize_stages(self.stage_timings)
        session_stage_summary = summarize_stages(self.session_stage_timings)
        configured_total = sum(self.configured_recipe_weights.values())
        recipe_mix = {
            recipe: {
                "configured_fraction": (self.configured_recipe_weights.get(recipe, 0.0) / configured_total) if configured_total else 0.0,
                "observed_fraction": self.recipe_counts.get(recipe, 0) / self.accepted if self.accepted else 0.0,
                "observed_count": self.recipe_counts.get(recipe, 0),
            }
            for recipe in sorted(set(self.configured_recipe_weights) | set(self.recipe_counts))
        }
        qa_summary = {
            key: {
                "mean": float(mean(values)),
                "min": float(min(values)),
                "max": float(max(values)),
            }
            for key, values in self.background_qa.items()
        }
        rejected_candidates = sum(self.rejection_reasons.values())
        configured_group_total = sum(self.configured_foreground_group_weights.values())
        observed_group_total = sum(self.foreground_group_counts.values())
        foreground_group_mix = {
            group: {
                "configured_fraction": self.configured_foreground_group_weights.get(group, 0.0) / configured_group_total
                if configured_group_total
                else None,
                "observed_fraction": self.foreground_group_counts.get(group, 0) / observed_group_total if observed_group_total else 0.0,
                "observed_count": self.foreground_group_counts.get(group, 0),
            }
            for group in sorted(set(self.configured_foreground_group_weights) | set(self.foreground_group_counts))
        }
        return {
            "accepted_samples": self.accepted,
            "session_accepted_samples": max(0, self.accepted - self.baseline_accepted),
            "target_samples": self.target,
            "candidate_attempts": self.candidate_attempts,
            "session_candidate_attempts": max(0, self.candidate_attempts - self.baseline_candidate_attempts),
            "elapsed_seconds": self.elapsed_seconds,
            "wall_elapsed_seconds": self.wall_elapsed_seconds,
            "paused_seconds": self.paused_seconds,
            "throughput_images_per_second": self.throughput,
            "rejection_reasons": self.rejection_reasons,
            "candidate_rejection_rate": rejected_candidates / self.candidate_attempts if self.candidate_attempts else 0.0,
            "background_rejection_rate": self.rejection_reasons.get("BackgroundSynthesisError", 0) / self.candidate_attempts if self.candidate_attempts else 0.0,
            "rejection_cost_ns": self.rejection_costs,
            "class_counts": self.class_counts,
            "foreground_group_counts": self.foreground_group_counts,
            "foreground_group_mix": foreground_group_mix,
            "recipe_counts": self.recipe_counts,
            "recipe_mix": recipe_mix,
            "negative_count": self.negative_count,
            "mask_archive_bytes": self.mask_archive_bytes,
            "mean_mask_archive_bytes": self.mask_archive_bytes / self.accepted if self.accepted else 0.0,
            "segmentation_qa": {
                "projections": len(self.segmentation_ious),
                "minimum_iou": min(self.segmentation_ious, default=None),
                "maximum_area_error": max(self.segmentation_area_errors, default=None),
                "warning_instances": self.segmentation_warning_instances,
            },
            "object_attempts": self.object_attempts,
            "object_rejections": self.object_rejections,
            "object_rejection_rate": self.object_rejections / self.object_attempts if self.object_attempts else 0.0,
            "background_qa": qa_summary,
            "background_warnings": self.background_warnings,
            "stage_timings": stage_summary,
            "session_stage_timings": session_stage_summary,
            "resource_peaks": self.resource_peaks,
            "workers": {"configured": self.worker_count, "active": self.active_workers, "in_flight": self.in_flight, "queued": self.queued},
            "run_state": self.run_state,
        }


class ResourceSampler:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.process.cpu_percent(None)
        self.last_sample_at = float("-inf")

    def sample_if_due(self, interval_seconds: float, *, force: bool = False) -> dict[str, Any] | None:
        now = perf_counter()
        if not force and now - self.last_sample_at < interval_seconds:
            return None
        self.last_sample_at = now
        return self.sample()

    def sample(self) -> dict[str, Any]:
        processes = [self.process, *self.process.children(recursive=True)]
        cpu_percent = 0.0
        rss_bytes = 0
        read_bytes = 0
        write_bytes = 0
        for process in processes:
            try:
                io = process.io_counters()
                memory = process.memory_info()
                cpu_percent += process.cpu_percent(None)
                rss_bytes += int(memory.rss)
                read_bytes += int(getattr(io, "read_bytes", 0))
                write_bytes += int(getattr(io, "write_bytes", 0))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {
            "timestamp_seconds": perf_counter(),
            "cpu_percent": cpu_percent,
            "rss_bytes": rss_bytes,
            "read_bytes": read_bytes,
            "write_bytes": write_bytes,
        }


class RunReporter:
    def __init__(
        self,
        mode: DisplayMode,
        refresh_hz: float,
        target: int,
        console: Console | None = None,
        plain_interval_seconds: float = 5.0,
        controls_description: str = "external run-control commands",
        pool_path: str | None = None,
    ) -> None:
        self.console = console or Console()
        if mode == "auto":
            if self.console.is_interactive:
                self.mode = "full" if self.console.width >= 100 and self.console.size.height >= 30 else "live"
            else:
                self.mode = "plain"
        else:
            self.mode = mode
        self.refresh_hz = refresh_hz
        self.target = target
        self.plain_interval_seconds = plain_interval_seconds
        self.controls_description = controls_description
        self.pool_path = pool_path
        self.live: Live | None = None
        self.last_plain = 0.0

    def start(self, metrics: MetricsAggregator) -> None:
        if self.mode in {"live", "full"}:
            self.live = Live(
                self._render(metrics),
                console=self.console,
                refresh_per_second=self.refresh_hz,
                screen=self.mode == "full",
                transient=True,
            )
            self.live.start()

    def update(self, metrics: MetricsAggregator, *, force: bool = False) -> None:
        if self.live is not None:
            self.live.update(self._render(metrics), refresh=force)
        elif self.mode == "plain":
            now = perf_counter()
            if force or now - self.last_plain >= self.plain_interval_seconds:
                self.console.print(
                    f"progress {metrics.accepted}/{metrics.target} | attempts {metrics.candidate_attempts} | "
                    f"{metrics.throughput:.2f} images/s | rejections {sum(metrics.rejection_reasons.values())}"
                )
                self.last_plain = now

    def finish(self, summary: dict[str, Any]) -> None:
        if self.live is not None:
            self.live.stop()
            self.live = None
        if self.mode != "quiet":
            status = summary.get("status", "unknown")
            color = "green" if status == "complete" else "yellow"
            self.console.print(
                Group(
                    Panel(
                        f"[{color}]{status}[/] — {summary.get('accepted_samples', 0)}/{summary.get('target_samples', 0)} samples",
                        title="Persistent run results",
                    ),
                    Columns(
                        [
                            Panel(
                                f"Active {summary.get('elapsed_seconds', 0.0):.2f}s\n"
                                f"Paused {summary.get('paused_seconds', 0.0):.2f}s\n"
                                f"{summary.get('throughput_images_per_second', 0.0):.2f} images/s",
                                title="Performance",
                            ),
                            Panel(
                                f"Rejections {sum(summary.get('rejection_reasons', {}).values())}\n"
                                f"Object reject rate {summary.get('object_rejection_rate', 0.0):.1%}\n"
                                f"QA {self.pool_path + '/qa/index.html' if self.pool_path else 'see pool/qa'}",
                                title="Quality",
                            ),
                        ],
                        expand=True,
                    ),
                    Panel(
                        f"Pool: {self.pool_path or summary.get('pool_path', 'unknown')}\n"
                        f"Next: run inspect {self.pool_path or summary.get('pool_path', 'OUTPUT_DIR')}",
                        title="Audit and follow-up",
                    ),
                )
            )

    def _render(self, metrics: MetricsAggregator) -> Group:
        progress = Table(expand=True, show_header=False)
        progress.add_column("Metric")
        progress.add_column("Value", justify="right")
        eta = metrics.eta_seconds
        progress.add_row("Accepted", f"{metrics.accepted}/{metrics.target}")
        progress.add_row("Run state", metrics.run_state)
        progress.add_row("Attempts", str(metrics.candidate_attempts))
        progress.add_row("Workers", f"{metrics.active_workers}/{metrics.worker_count} active | {metrics.in_flight} in flight | {metrics.queued} queued")

        performance = Table(expand=True, show_header=False)
        performance.add_column("Metric")
        performance.add_column("Value", justify="right")
        performance.add_row("Throughput", f"{metrics.throughput:.2f} images/s")
        performance.add_row("Estimated time remaining", f"{eta:.1f}s" if metrics.throughput > 0 else "—")
        quality_lines = [f"Candidate rejections: {sum(metrics.rejection_reasons.values())}"]
        if metrics.object_attempts:
            quality_lines.append(f"Object rejects: {metrics.object_rejections}/{metrics.object_attempts} ({metrics.object_rejections / metrics.object_attempts:.1%})")
        if metrics.rejection_reasons:
            top = sorted(metrics.rejection_reasons.items(), key=lambda item: item[1], reverse=True)[:3]
            quality_lines.append("Top: " + ", ".join(f"{key}:{value}" for key, value in top))
        distributions: list[str] = []
        if metrics.recipe_counts:
            configured_total = sum(metrics.configured_recipe_weights.values())
            recipe_text = []
            for key in sorted(set(metrics.configured_recipe_weights) | set(metrics.recipe_counts)):
                configured = metrics.configured_recipe_weights.get(key, 0.0) / configured_total if configured_total else 0.0
                observed = metrics.recipe_counts.get(key, 0) / metrics.accepted if metrics.accepted else 0.0
                recipe_text.append(f"{key} {observed:.0%}/{configured:.0%}")
            distributions.append("Recipes obs/cfg: " + ", ".join(recipe_text))
        if metrics.class_counts:
            top_classes = sorted(metrics.class_counts.items(), key=lambda item: item[1], reverse=True)[:5]
            distributions.append("Classes: " + ", ".join(f"{name}:{count}" for name, count in top_classes))
        if metrics.foreground_group_counts:
            distributions.append("Groups: " + ", ".join(f"{name}:{count}" for name, count in sorted(metrics.foreground_group_counts.items())))
        distributions.append(f"Negatives: {metrics.negative_count}")
        warning_lines: list[str] = []
        if metrics.background_warnings:
            top_warnings = sorted(metrics.background_warnings.items(), key=lambda item: item[1], reverse=True)[:3]
            warning_lines.extend(f"{name}: {count}" for name, count in top_warnings)
        if metrics.stage_timings:
            slowest = max(metrics.stage_timings, key=lambda key: sum(metrics.stage_timings[key]) / len(metrics.stage_timings[key]))
            ordered = sorted(metrics.stage_timings[slowest])
            p50 = ordered[len(ordered) // 2] / 1_000_000
            p95 = ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))] / 1_000_000
            performance.add_row("Bottleneck p50/p95", f"{slowest} {p50:.1f}/{p95:.1f} ms")
        if metrics.resource_peaks:
            performance.add_row(
                "Resources",
                f"CPU {metrics.resource_peaks.get('cpu_percent', 0):.0f}% | "
                f"RSS {metrics.resource_peaks.get('rss_bytes', 0) / 1024 / 1024:.1f} MiB | "
                f"I/O R/W {metrics.resource_peaks.get('read_bytes', 0) / 1024 / 1024:.1f}/"
                f"{metrics.resource_peaks.get('write_bytes', 0) / 1024 / 1024:.1f} MiB",
            )
        return Group(
            Panel(progress, title="Progress"),
            Columns(
                [
                    Panel("\n".join(quality_lines), title="Quality"),
                    Panel(performance, title="Performance"),
                ],
                expand=True,
            ),
            Panel("\n".join(distributions), title="Distributions"),
            Columns(
                [
                    Panel("\n".join(warning_lines) or "none", title="Warnings"),
                    Panel(self.controls_description, title="Controls"),
                ],
                expand=True,
            ),
        )
