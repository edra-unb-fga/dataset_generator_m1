from __future__ import annotations

import time
import subprocess
import sys

import psutil

from dataset_generator_m1.resource_monitor import ProcessTreeMonitor, ProcessTreeSampler


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def snapshot(value: int = 1) -> dict:
    def group(count: int, multiplier: int = 1) -> dict:
        return {
            "process_count": count,
            "cpu_percent": float(value * multiplier),
            "rss_bytes": value * multiplier * 100,
            "read_bytes": value * multiplier * 10,
            "write_bytes": value * multiplier * 20,
        }

    return {
        "coordinator": group(1),
        "direct_workers": group(2, 2),
        "other_descendants": group(1, 3),
        "aggregate": group(4, 6),
        "sample_errors": 0,
    }


def test_monitor_records_state_sessions_and_bounded_overflow() -> None:
    clock = FakeClock()
    monitor = ProcessTreeMonitor(
        interval_seconds=1.0,
        sampler=lambda: snapshot(2),
        clock=clock,
        capacity=2,
        session_id="session-test",
    )

    monitor.sample_once()
    clock.value += 1
    monitor.set_run_state("paused")
    monitor.sample_once()
    clock.value += 1
    monitor.sample_once()
    records = monitor.drain()

    assert records[0]["metric_type"] == "resource_monitor_warning"
    assert records[0]["code"] == "RESOURCE_SAMPLES_DROPPED"
    assert records[0]["dropped_samples"] == 1
    samples = records[1:]
    assert [item["sequence"] for item in samples] == [1, 2]
    assert {item["session_id"] for item in samples} == {"session-test"}
    assert all(item["run_state"] == "paused" for item in samples)
    assert samples[-1]["elapsed_seconds"] == 2.0
    assert "hostname" not in str(records).lower()
    assert "pid" not in str(records).lower()


def test_threaded_monitor_stops_and_flushes() -> None:
    calls = [0]

    def sampler() -> dict:
        calls[0] += 1
        return snapshot(calls[0])

    monitor = ProcessTreeMonitor(interval_seconds=0.01, sampler=sampler, capacity=32)
    monitor.start()
    deadline = time.monotonic() + 1.0
    while calls[0] < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    monitor.set_run_state("stopping")
    monitor.stop()

    records = [item for item in monitor.drain() if item["metric_type"] == "process_tree_resource"]
    assert len(records) >= 3
    assert records[-1]["run_state"] == "stopping"
    assert monitor.is_running is False


class FakeProcess:
    def __init__(self, pid: int, *, children: list["FakeProcess"] | None = None, missing: bool = False) -> None:
        self.pid = pid
        self._children = children or []
        self.missing = missing

    def children(self, recursive: bool = False):
        if not recursive:
            return list(self._children)
        result = list(self._children)
        for child in self._children:
            result.extend(child.children(recursive=True))
        return result

    def cpu_percent(self, _interval=None):
        if self.missing:
            raise psutil.NoSuchProcess(self.pid)
        return float(self.pid)

    def memory_info(self):
        if self.missing:
            raise psutil.NoSuchProcess(self.pid)
        return type("Memory", (), {"rss": self.pid * 100})()

    def io_counters(self):
        return type("IO", (), {"read_bytes": self.pid * 10, "write_bytes": self.pid * 20})()


def test_sampler_classifies_tree_and_tolerates_disappearing_children() -> None:
    grandchild = FakeProcess(4)
    direct = FakeProcess(2, children=[grandchild])
    vanished = FakeProcess(3, missing=True)
    root = FakeProcess(1, children=[direct, vanished])

    result = ProcessTreeSampler(root_process=root).sample()

    assert result["coordinator"]["process_count"] == 1
    assert result["direct_workers"]["process_count"] == 1
    assert result["other_descendants"]["process_count"] == 1
    assert result["aggregate"]["process_count"] == 3
    assert result["aggregate"]["rss_bytes"] == 700
    assert result["sample_errors"] == 1


def test_sampler_observes_then_releases_a_short_lived_child() -> None:
    sampler = ProcessTreeSampler()
    baseline_count = sampler.sample()["direct_workers"]["process_count"]
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.4)"])
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            active = sampler.sample()
            if active["direct_workers"]["process_count"] >= baseline_count + 1:
                break
            time.sleep(0.02)
        active_count = active["direct_workers"]["process_count"]
        assert active_count >= baseline_count + 1
    finally:
        child.wait(timeout=2)

    after = sampler.sample()
    assert after["aggregate"]["process_count"] >= 1
    assert after["direct_workers"]["process_count"] <= active_count - 1
