from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any

import cv2
import psutil

from .memory_planning import HEADROOM_PERCENT, memory_components, source_shapes


def usable_cpu_count():
    logical = os.cpu_count() or 1
    try:
        return max(1, min(logical, len(psutil.Process().cpu_affinity())))
    except (AttributeError, psutil.Error):
        return logical


def resolve_worker_count(value: str | int | None, resolved: Any | None = None) -> int:
    if resolved is not None:
        return plan_execution(resolved, value).workers
    if value is None:
        value = resolved.profile.execution.workers if resolved is not None else 1
    if value == "auto":
        cpu_limit = max(1, usable_cpu_count() - 1)
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


@dataclass(frozen=True)
class ExecutionPlan:
    workers: int
    native_threads: int | None
    max_in_flight: int
    cache_bytes_per_worker: int
    estimated_peak_bytes: int
    ram_budget_bytes: int
    cpu_budget: int
    warnings: tuple[str, ...]
    requested: dict[str, Any]
    memory_estimate: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_execution(resolved: Any, workers: str | int | None = None, *, available_ram: int | None = None,
                   logical_cpus: int | None = None) -> ExecutionPlan:
    """One advisory hardware plan; only cache/queue bounds are hard memory guarantees."""
    policy = resolved.profile.execution
    requested = policy.model_dump(mode="json")
    selected = policy.workers if workers is None else workers
    cpus = logical_cpus or usable_cpu_count()
    cpu_budget = policy.cpu_budget or max(1, cpus - 1)
    ram = available_ram if available_ram is not None else psutil.virtual_memory().available
    ram_budget = policy.ram_budget_mb * 1024**2 if policy.ram_budget_mb else int(ram * .6)
    total_cache = policy.decoded_cache_mb * 1024**2
    native_threads = policy.native_threads or (1 if policy.cpu_budget is not None or policy.workers == "auto" or selected == "auto" else None)
    thread_budget = native_threads or 1
    effective_native_threads = native_threads or max(1, cv2.getNumThreads())
    shapes = source_shapes(resolved)

    def estimate(count):
        window = policy.max_in_flight or count * 2
        components = memory_components(resolved, count, window, effective_native_threads, shapes)
        # LRU payload is a hard limit; reserve allocator/copy headroom above it.
        components["decoded_cache_bytes"] = total_cache
        components["cache_headroom_bytes"] = (total_cache * HEADROOM_PERCENT + 99) // 100
        components["estimated_peak_bytes"] += total_cache + components["cache_headroom_bytes"]
        return window, components

    if selected == "auto":
        maximum = max(1, min(32, cpu_budget // thread_budget, cpus // thread_budget, policy.max_in_flight or 32))
        count = 1
        for candidate in range(maximum, 0, -1):
            if estimate(candidate)[1]["estimated_peak_bytes"] <= ram_budget:
                count = candidate
                break
    else:
        count = int(selected)
        if count < 1:
            raise ValueError("workers must be auto or an integer >= 1")
    if policy.cpu_budget is not None and count * thread_budget > cpu_budget:
        raise ValueError("workers × requested native_threads exceeds cpu_budget; adjust execution explicitly")
    window, components = estimate(count)
    if window < count:
        raise ValueError("max_in_flight must be at least the effective worker count")
    if total_cache > ram_budget:
        raise ValueError("Decoded cache alone exceeds ram_budget_mb")
    estimated = components["estimated_peak_bytes"]
    warnings = []
    if estimated > ram_budget:
        warnings.append("RAM_ESTIMATE_EXCEEDS_BUDGET: advisory estimate; lower workers/queue/cache explicitly")
    if cpu_budget > cpus:
        warnings.append("CPU_BUDGET_EXCEEDS_DETECTED_LOGICAL_CPUS")
    if ram_budget > ram:
        warnings.append("RAM_BUDGET_EXCEEDS_CURRENTLY_AVAILABLE_MEMORY")
    if native_threads is None and count > 1:
        warnings.append("NATIVE_THREADS_UNBOUNDED: backend defaults may oversubscribe CPUs")
    if count * effective_native_threads > cpus:
        warnings.append("NATIVE_THREADS_OVERSUBSCRIBED: workers × effective OpenCV threads exceeds detected logical CPUs")
    if shapes["unknown_sources"]:
        warnings.append("SOURCE_DIMENSIONS_INCOMPLETE: memory estimate uses fallback sizes; validate source assets")
    return ExecutionPlan(count, native_threads, window, total_cache // count, estimated, ram_budget,
                         cpu_budget, tuple(warnings), {**requested, "workers": selected}, components)


def format_execution_plan(plan):
    native = plan['native_threads'] if plan['native_threads'] is not None else 'backend default'
    return (f"Execution: {plan['workers']} workers, OpenCV threads/worker: {native}, "
            f"in-flight: {plan['max_in_flight']}\n"
            f"Advisory RSS: {plan['estimated_peak_bytes']/2**30:.2f} GiB; "
            f"planning budget: {plan['ram_budget_bytes']/2**30:.2f} GiB\n"
            "Capacity planning does not predict the fastest setting; use execution candidates/recommend for local tuning.")


@contextmanager
def execution_scope(plan: ExecutionPlan):
    """Bound process-local decoded storage and restore OpenCV thread state reliably."""
    from .decoded_cache import cache_scope
    previous = cv2.getNumThreads()
    try:
        if plan.native_threads is not None:
            cv2.setNumThreads(plan.native_threads)
        with cache_scope(plan.cache_bytes_per_worker):
            yield
    finally:
        cv2.setNumThreads(previous)


def initialize_worker(plan: ExecutionPlan) -> None:
    from .decoded_cache import configure_cache
    if plan.native_threads is not None:
        cv2.setNumThreads(plan.native_threads)
    configure_cache(plan.cache_bytes_per_worker)
