from __future__ import annotations

from collections import deque
from collections.abc import Callable
from threading import Event, Lock, Thread
from time import perf_counter
from typing import Any
from uuid import uuid4

import psutil


_RESOURCE_KEYS = ("cpu_percent", "rss_bytes", "read_bytes", "write_bytes")


def _empty_group() -> dict[str, float | int]:
    return {
        "process_count": 0,
        "cpu_percent": 0.0,
        "rss_bytes": 0,
        "read_bytes": 0,
        "write_bytes": 0,
    }


def _add_process(group: dict[str, float | int], process: Any) -> None:
    io = process.io_counters()
    memory = process.memory_info()
    cpu_percent = float(process.cpu_percent(None))
    group["process_count"] = int(group["process_count"]) + 1
    group["cpu_percent"] = float(group["cpu_percent"]) + cpu_percent
    group["rss_bytes"] = int(group["rss_bytes"]) + int(memory.rss)
    group["read_bytes"] = int(group["read_bytes"]) + int(getattr(io, "read_bytes", 0))
    group["write_bytes"] = int(group["write_bytes"]) + int(getattr(io, "write_bytes", 0))


class ProcessTreeSampler:
    """Collect one sanitized snapshot of the coordinator and its current descendants."""

    def __init__(self, root_process: Any | None = None) -> None:
        self.root = root_process or psutil.Process()
        self._process_cache: dict[int, Any] = {self.root.pid: self.root}
        try:
            self.root.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def sample(self) -> dict[str, Any]:
        groups = {
            "coordinator": _empty_group(),
            "direct_workers": _empty_group(),
            "other_descendants": _empty_group(),
        }
        errors = 0
        try:
            direct = list(self.root.children(recursive=False))
            descendants = list(self.root.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            direct, descendants = [], []
            errors += 1
        direct_ids = {process.pid for process in direct}
        seen: set[int] = set()
        classified = [("coordinator", self.root)]
        classified.extend(
            (
                "direct_workers" if process.pid in direct_ids else "other_descendants",
                self._process_cache.setdefault(process.pid, process),
            )
            for process in descendants
        )
        for group_name, process in classified:
            if process.pid in seen:
                continue
            seen.add(process.pid)
            try:
                _add_process(groups[group_name], process)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                errors += 1
                self._process_cache.pop(process.pid, None)
        self._process_cache = {
            pid: process for pid, process in self._process_cache.items() if pid in seen
        }
        aggregate = _empty_group()
        for group in groups.values():
            aggregate["process_count"] = int(aggregate["process_count"]) + int(group["process_count"])
            for key in _RESOURCE_KEYS:
                aggregate[key] = float(aggregate[key]) + float(group[key])
        for key in ("rss_bytes", "read_bytes", "write_bytes"):
            aggregate[key] = int(aggregate[key])
        return {**groups, "aggregate": aggregate, "sample_errors": errors}


class ProcessTreeMonitor:
    """Continuously sample a process tree and expose bounded records for coordinator-owned writes."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        sampler: Callable[[], dict[str, Any]] | None = None,
        clock: Callable[[], float] = perf_counter,
        capacity: int = 256,
        session_id: str | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("resource monitor interval must be positive")
        if capacity < 1:
            raise ValueError("resource monitor capacity must be >= 1")
        self.sampler = sampler or ProcessTreeSampler().sample
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.capacity = capacity
        self.session_id = session_id or f"resource-{uuid4().hex[:12]}"
        self.started_at = clock()
        self.run_state = "running"
        self.sequence = 0
        self._buffer: deque[dict[str, Any]] = deque()
        self._dropped = 0
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def set_run_state(self, state: str) -> None:
        with self._lock:
            self.run_state = state

    def _append(self, record: dict[str, Any]) -> None:
        with self._lock:
            if len(self._buffer) >= self.capacity:
                self._buffer.popleft()
                self._dropped += 1
            self._buffer.append(record)

    def sample_once(self) -> None:
        with self._lock:
            state = self.run_state
            sequence = self.sequence
            self.sequence += 1
        try:
            snapshot = self.sampler()
            record = {
                "schema_version": 1,
                "metric_type": "process_tree_resource",
                "session_id": self.session_id,
                "sequence": sequence,
                "elapsed_seconds": max(0.0, self.clock() - self.started_at),
                "run_state": state,
                **snapshot,
            }
        except Exception as exc:
            record = {
                "schema_version": 1,
                "metric_type": "resource_monitor_warning",
                "session_id": self.session_id,
                "sequence": sequence,
                "elapsed_seconds": max(0.0, self.clock() - self.started_at),
                "run_state": state,
                "code": "RESOURCE_SAMPLE_FAILED",
                "message": f"{type(exc).__name__} while sampling the process tree",
            }
        self._append(record)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.sample_once()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self.sample_once()
        self._thread = Thread(target=self._run, name="resource-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
        self._thread = None
        self.sample_once()

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._buffer)
            self._buffer.clear()
            dropped = self._dropped
            self._dropped = 0
            state = self.run_state
        if dropped:
            records.insert(
                0,
                {
                    "schema_version": 1,
                    "metric_type": "resource_monitor_warning",
                    "session_id": self.session_id,
                    "run_state": state,
                    "code": "RESOURCE_SAMPLES_DROPPED",
                    "dropped_samples": dropped,
                },
            )
        return records
