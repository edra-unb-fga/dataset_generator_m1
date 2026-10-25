from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any

import cv2
import psutil


def resolve_worker_count(value: str | int | None, resolved: Any | None = None) -> int:
    if resolved is not None:
        return plan_execution(resolved, value).workers
    if value is None:
        value = resolved.profile.execution.workers if resolved is not None else 1
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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_execution(resolved: Any, workers: str | int | None = None, *, available_ram: int | None = None,
                   logical_cpus: int | None = None) -> ExecutionPlan:
    """One advisory hardware plan; only cache/queue bounds are hard memory guarantees."""
    policy = resolved.profile.execution
    requested = policy.model_dump(mode="json")
    selected = policy.workers if workers is None else workers
    cpus = logical_cpus or os.cpu_count() or 1
    cpu_budget = policy.cpu_budget or max(1, cpus - 1)
    ram = available_ram if available_ram is not None else psutil.virtual_memory().available
    ram_budget = policy.ram_budget_mb * 1024**2 if policy.ram_budget_mb else int(ram * .6)
    width, height = resolved.profile.output.image_size
    # Include decoded sources, float synthesis workspaces and output/mask return buffers.
    # Large source decodes can exceed this heuristic; RAM remains advisory.
    source_pixels = 2 * width * height
    work_bytes = max(256 * 1024**2, int(width * height * resolved.profile.scene.canvas_scale**2 * 64 + source_pixels * 4))
    if resolved.profile.scene.lighting is not None:
        work_bytes += width*min(height, 128)*40 + width*height*3
    total_cache = policy.decoded_cache_mb * 1024**2
    native_threads = policy.native_threads or (1 if policy.cpu_budget is not None else None)
    thread_budget = native_threads or 1
    if selected == "auto":
        count = max(1, min(32, cpu_budget // thread_budget, max(0, ram_budget - total_cache) // work_bytes))
    else:
        count = int(selected)
        if count < 1:
            raise ValueError("workers must be auto or an integer >= 1")
    if policy.cpu_budget is not None and count * thread_budget > cpu_budget:
        raise ValueError("workers × requested native_threads exceeds cpu_budget; adjust execution explicitly")
    window = policy.max_in_flight or count * 2
    if window < count:
        raise ValueError("max_in_flight must be at least the effective worker count")
    if total_cache > ram_budget:
        raise ValueError("Decoded cache alone exceeds ram_budget_mb")
    estimated = count * work_bytes + window * width * height * (3 + 2 * resolved.profile.sampling.instances_per_image[1]) + total_cache
    warnings = []
    if estimated > ram_budget:
        warnings.append("RAM_ESTIMATE_EXCEEDS_BUDGET: advisory estimate; lower workers/queue/cache explicitly")
    if cpu_budget > cpus:
        warnings.append("CPU_BUDGET_EXCEEDS_DETECTED_LOGICAL_CPUS")
    if ram_budget > ram:
        warnings.append("RAM_BUDGET_EXCEEDS_CURRENTLY_AVAILABLE_MEMORY")
    if native_threads is None and count > 1:
        warnings.append("NATIVE_THREADS_UNBOUNDED: backend defaults may oversubscribe CPUs")
    return ExecutionPlan(count, native_threads, window, total_cache // count, estimated, ram_budget,
                         cpu_budget, tuple(warnings), {**requested, "workers": selected})


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
