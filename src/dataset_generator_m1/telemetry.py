from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from statistics import mean, median
from time import perf_counter, perf_counter_ns
from typing import Any, Callable, Literal

import psutil
from rich.console import Console
from rich.live import Live
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
    started_at: float = field(default_factory=perf_counter)
    accepted: int = 0
    candidate_attempts: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    stage_timings: dict[str, list[int]] = field(default_factory=dict)
    class_counts: dict[str, int] = field(default_factory=dict)
    recipe_counts: dict[str, int] = field(default_factory=dict)
    foreground_group_counts: dict[str, int] = field(default_factory=dict)
    negative_count: int = 0
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

    def record_sample(self, record: dict[str, Any]) -> None:
        self.accepted += 1
        self.candidate_attempts += 1
        for stage, duration in record.get("stage_timings_ns", {}).items():
            self.stage_timings.setdefault(stage, []).append(int(duration))
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
        for key, value in background.get("qa", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.background_qa.setdefault(str(key), []).append(float(value))
        for warning in background.get("warnings", []):
            self.background_warnings[str(warning)] = self.background_warnings.get(str(warning), 0) + 1
        if record.get("intentional_negative"):
            self.negative_count += 1

    def record_rejection(self, record: dict[str, Any]) -> None:
        self.candidate_attempts += 1
        reason = str(record.get("reason", "unknown"))
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
        self.rejection_costs[reason] = self.rejection_costs.get(reason, 0) + sum(
            int(duration) for duration in record.get("stage_timings_ns", {}).values()
        )
        for stage, duration in record.get("stage_timings_ns", {}).items():
            self.stage_timings.setdefault(stage, []).append(int(duration))

    def record_resource(self, record: dict[str, Any]) -> None:
        for key in ("cpu_percent", "rss_bytes", "read_bytes", "write_bytes"):
            value = float(record.get(key, 0.0))
            self.resource_peaks[key] = max(self.resource_peaks.get(key, 0.0), value)

    def set_workload(self, *, worker_count: int, active_workers: int, in_flight: int, queued: int) -> None:
        self.worker_count = worker_count
        self.active_workers = active_workers
        self.in_flight = in_flight
        self.queued = queued

    @property
    def elapsed_seconds(self) -> float:
        return max(1e-9, perf_counter() - self.started_at)

    @property
    def throughput(self) -> float:
        return self.accepted / self.elapsed_seconds

    def summary(self) -> dict[str, Any]:
        stage_summary: dict[str, dict[str, float | int]] = {}
        for stage, values in self.stage_timings.items():
            ordered = sorted(values)

            def percentile(fraction: float) -> int:
                if not ordered:
                    return 0
                return int(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))])

            stage_summary[stage] = {
                "count": len(values),
                "total_ns": int(sum(values)),
                "mean_ns": int(mean(values)),
                "median_ns": int(median(values)),
                "p90_ns": percentile(0.90),
                "p95_ns": percentile(0.95),
                "p99_ns": percentile(0.99),
            }
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
            "target_samples": self.target,
            "candidate_attempts": self.candidate_attempts,
            "elapsed_seconds": self.elapsed_seconds,
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
            "object_attempts": self.object_attempts,
            "object_rejections": self.object_rejections,
            "object_rejection_rate": self.object_rejections / self.object_attempts if self.object_attempts else 0.0,
            "background_qa": qa_summary,
            "background_warnings": self.background_warnings,
            "stage_timings": stage_summary,
            "resource_peaks": self.resource_peaks,
            "workers": {"configured": self.worker_count, "active": self.active_workers, "in_flight": self.in_flight, "queued": self.queued},
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
    ) -> None:
        self.console = console or Console()
        self.mode: DisplayMode = "live" if mode == "auto" and self.console.is_interactive else ("plain" if mode == "auto" else mode)
        self.refresh_hz = refresh_hz
        self.target = target
        self.plain_interval_seconds = plain_interval_seconds
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
            self.console.print(
                f"[{ 'green' if status == 'complete' else 'yellow' }]run {status}[/] | "
                f"accepted {summary.get('accepted_samples', 0)}/{summary.get('target_samples', 0)} | "
                f"elapsed {summary.get('elapsed_seconds', 0.0):.2f}s"
            )

    def _render(self, metrics: MetricsAggregator) -> Table:
        table = Table(title="Dataset Generator M1", expand=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        remaining = max(0, metrics.target - metrics.accepted)
        eta = remaining / metrics.throughput if metrics.throughput > 0 else 0.0
        table.add_row("Accepted", f"{metrics.accepted}/{metrics.target}")
        table.add_row("Attempts", str(metrics.candidate_attempts))
        table.add_row("Workers", f"{metrics.active_workers}/{metrics.worker_count} active | {metrics.in_flight} in flight | {metrics.queued} queued")
        table.add_row("Throughput", f"{metrics.throughput:.2f} images/s")
        table.add_row("ETA", f"{eta:.1f}s" if metrics.throughput > 0 else "—")
        table.add_row("Rejections", str(sum(metrics.rejection_reasons.values())))
        if metrics.object_attempts:
            table.add_row("Object rejects", f"{metrics.object_rejections}/{metrics.object_attempts} ({metrics.object_rejections / metrics.object_attempts:.1%})")
        if metrics.rejection_reasons:
            top = sorted(metrics.rejection_reasons.items(), key=lambda item: item[1], reverse=True)[:3]
            table.add_row("Top rejection", ", ".join(f"{key}:{value}" for key, value in top))
        if metrics.recipe_counts:
            configured_total = sum(metrics.configured_recipe_weights.values())
            recipe_text = []
            for key in sorted(set(metrics.configured_recipe_weights) | set(metrics.recipe_counts)):
                configured = metrics.configured_recipe_weights.get(key, 0.0) / configured_total if configured_total else 0.0
                observed = metrics.recipe_counts.get(key, 0) / metrics.accepted if metrics.accepted else 0.0
                recipe_text.append(f"{key} {observed:.0%}/{configured:.0%}")
            table.add_row("Recipes obs/cfg", ", ".join(recipe_text))
        if metrics.class_counts:
            top_classes = sorted(metrics.class_counts.items(), key=lambda item: item[1], reverse=True)[:5]
            table.add_row("Classes", ", ".join(f"{name}:{count}" for name, count in top_classes))
        if metrics.foreground_group_counts:
            table.add_row("Groups", ", ".join(f"{name}:{count}" for name, count in sorted(metrics.foreground_group_counts.items())))
        table.add_row("Negatives", str(metrics.negative_count))
        if metrics.background_warnings:
            top_warnings = sorted(metrics.background_warnings.items(), key=lambda item: item[1], reverse=True)[:3]
            table.add_row("Warnings", ", ".join(f"{name}:{count}" for name, count in top_warnings))
        if metrics.stage_timings:
            slowest = max(metrics.stage_timings, key=lambda key: sum(metrics.stage_timings[key]) / len(metrics.stage_timings[key]))
            ordered = sorted(metrics.stage_timings[slowest])
            p50 = ordered[len(ordered) // 2] / 1_000_000
            p95 = ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))] / 1_000_000
            table.add_row("Bottleneck p50/p95", f"{slowest} {p50:.1f}/{p95:.1f} ms")
        if metrics.resource_peaks:
            table.add_row(
                "Resources",
                f"CPU {metrics.resource_peaks.get('cpu_percent', 0):.0f}% | "
                f"RSS {metrics.resource_peaks.get('rss_bytes', 0) / 1024 / 1024:.1f} MiB | "
                f"I/O R/W {metrics.resource_peaks.get('read_bytes', 0) / 1024 / 1024:.1f}/"
                f"{metrics.resource_peaks.get('write_bytes', 0) / 1024 / 1024:.1f} MiB",
            )
        return table
