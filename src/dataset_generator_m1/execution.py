from __future__ import annotations

import os
from typing import Any

import psutil


def resolve_worker_count(value: str | int | None, resolved: Any | None = None) -> int:
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
