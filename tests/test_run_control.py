import json
import sys
import time
from types import SimpleNamespace
from pathlib import Path

from dataset_generator_m1.run_control import RunController, TerminalControlAdapter, request_run_action, run_status


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_external_requests_are_atomic_and_audited(tmp_path: Path) -> None:
    controller = RunController.open(tmp_path, resume=False)

    paused = request_run_action(tmp_path, "pause")

    assert paused["desired_state"] == "paused"
    assert run_status(tmp_path)["effective_state"] == "draining"
    events = [json.loads(line) for line in (tmp_path / "control-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events] == ["created", "pause-requested"]
    assert not (tmp_path / "control.json.tmp").exists()
    assert controller.read()["desired_state"] == "paused"


def test_pause_waits_without_counting_paused_time(tmp_path: Path) -> None:
    clock = FakeClock()
    controller = RunController.open(tmp_path, resume=False, clock=clock)
    request_run_action(tmp_path, "pause", clock=clock)

    sleeps = 0

    def fake_sleep(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        clock.advance(seconds)
        if sleeps == 2:
            request_run_action(tmp_path, "continue", clock=clock)

    result = controller.checkpoint(sleep=fake_sleep, poll_seconds=2.0)

    assert result == "continue"
    assert controller.read()["actual_state"] == "running"
    assert controller.paused_seconds == 4.0
    events = [json.loads(line) for line in (tmp_path / "control-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events][-4:] == ["draining", "paused", "continue-requested", "continued"]


def test_pause_checkpoint_keeps_polling_coordinator_services(tmp_path: Path) -> None:
    clock = FakeClock()
    controller = RunController.open(tmp_path, resume=False, clock=clock)
    request_run_action(tmp_path, "pause", clock=clock)
    polls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        if len(polls) == 3:
            request_run_action(tmp_path, "continue", clock=clock)

    result = controller.checkpoint(
        sleep=fake_sleep,
        poll_seconds=0.5,
        on_poll=lambda: polls.append(clock()),
    )

    assert result == "continue"
    assert len(polls) == 3


def test_stop_during_pause_is_graceful_and_resumable(tmp_path: Path) -> None:
    clock = FakeClock()
    controller = RunController.open(tmp_path, resume=False, clock=clock)
    request_run_action(tmp_path, "pause", clock=clock)

    def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        request_run_action(tmp_path, "stop", clock=clock)

    assert controller.checkpoint(sleep=fake_sleep) == "stop"
    controller.finish("interrupted")
    assert run_status(tmp_path)["actual_state"] == "interrupted"

    resumed = RunController.open(tmp_path, resume=True, clock=clock)
    assert resumed.read()["actual_state"] == "running"
    assert resumed.read()["desired_state"] == "running"


def test_terminal_runs_reject_control_requests(tmp_path: Path) -> None:
    controller = RunController.open(tmp_path, resume=False)
    controller.finish("complete")

    try:
        request_run_action(tmp_path, "pause")
    except ValueError as exc:
        assert "terminal" in str(exc).lower()
    else:
        raise AssertionError("terminal run accepted a pause request")


def test_posix_terminal_adapter_restores_terminal_state(tmp_path: Path, monkeypatch) -> None:
    restored: list[object] = []
    fake_stdin = SimpleNamespace(fileno=lambda: 7, isatty=lambda: True, read=lambda _count: "")
    fake_termios = SimpleNamespace(
        TCSADRAIN=1,
        tcgetattr=lambda _fd: ["saved-state"],
        tcsetattr=lambda _fd, _when, state: restored.append(state),
    )
    fake_tty = SimpleNamespace(setcbreak=lambda _fd: None)

    def no_input(*_args):
        time.sleep(0.01)
        return ([], [], [])

    monkeypatch.setattr("dataset_generator_m1.run_control.sys.stdin", fake_stdin)
    monkeypatch.setitem(sys.modules, "termios", fake_termios)
    monkeypatch.setitem(sys.modules, "tty", fake_tty)
    monkeypatch.setitem(sys.modules, "select", SimpleNamespace(select=no_input))
    adapter = TerminalControlAdapter(tmp_path, enabled=False)
    adapter.backend = "posix"
    adapter.enabled = True

    adapter.start()
    adapter.stop()

    assert restored == [["saved-state"]]
