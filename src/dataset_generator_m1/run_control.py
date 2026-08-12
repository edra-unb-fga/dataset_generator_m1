from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep as default_sleep
from typing import Any, Callable, Literal


RunAction = Literal["pause", "continue", "stop"]
TERMINAL_STATES = {"complete", "interrupted", "failed"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read(root: Path) -> dict[str, Any]:
    path = root / "control.json"
    if not path.exists():
        raise FileNotFoundError(f"No controlled run exists at {root}")
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _record_lock(root: Path):
    """Serialize cross-process read/modify/write cycles around the atomic record."""
    lock_path = root / "control.lock"
    deadline = perf_counter() + 5.0
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if perf_counter() >= deadline:
                raise TimeoutError(f"Timed out waiting for run-control lock: {lock_path}")
            default_sleep(0.01)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _effective_state(record: dict[str, Any]) -> str:
    if record["actual_state"] == "running" and record["desired_state"] == "paused":
        return "draining"
    if record["actual_state"] == "running" and record["desired_state"] == "stopping":
        return "stopping"
    return str(record["actual_state"])


def run_status(root: str | Path) -> dict[str, Any]:
    record = _read(Path(root).resolve())
    return {"status": "valid", **record, "effective_state": _effective_state(record)}


def request_run_action(
    root: str | Path,
    action: RunAction,
    *,
    clock: Callable[[], float] = perf_counter,
) -> dict[str, Any]:
    root = Path(root).resolve()
    with _record_lock(root):
        record = _read(root)
        if record["actual_state"] in TERMINAL_STATES:
            raise ValueError(f"Run is terminal ({record['actual_state']}); it cannot accept {action}")
        desired = {"pause": "paused", "continue": "running", "stop": "stopping"}[action]
        record.update(
            {
                "desired_state": desired,
                "sequence": int(record.get("sequence", 0)) + 1,
                "updated_at": _timestamp(),
            }
        )
        _atomic_json(root / "control.json", record)
        _append_event(
            root / "control-events.jsonl",
            {
                "schema_version": 1,
                "event": f"{action}-requested",
                "sequence": record["sequence"],
                "timestamp": record["updated_at"],
                "monotonic_seconds": clock(),
                "actual_state": record["actual_state"],
                "desired_state": desired,
                "actor": "external",
            },
        )
    return run_status(root)


@dataclass
class RunController:
    root: Path
    clock: Callable[[], float] = field(default=perf_counter, repr=False)
    _pause_started: float | None = field(default=None, init=False, repr=False)
    _paused_total: float = field(default=0.0, init=False, repr=False)

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        resume: bool,
        clock: Callable[[], float] = perf_counter,
    ) -> "RunController":
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        controller = cls(root, clock)
        path = root / "control.json"
        if path.exists():
            if not resume:
                raise ValueError(f"Control record already exists; use --resume: {root}")
            controller._write_transition("running", desired="running", event="resumed")
        else:
            record = {
                "schema_version": 1,
                "actual_state": "running",
                "desired_state": "running",
                "sequence": 0,
                "created_at": _timestamp(),
                "updated_at": _timestamp(),
                "coordinator_pid": os.getpid(),
            }
            _atomic_json(path, record)
            controller._event("created", record, actor="coordinator")
        return controller

    @property
    def paused_seconds(self) -> float:
        current = self.clock() - self._pause_started if self._pause_started is not None else 0.0
        return self._paused_total + current

    def read(self) -> dict[str, Any]:
        return _read(self.root)

    def checkpoint(
        self,
        *,
        sleep: Callable[[float], None] = default_sleep,
        poll_seconds: float = 0.2,
        on_pause: Callable[[], None] | None = None,
        on_continue: Callable[[], None] | None = None,
        on_poll: Callable[[], None] | None = None,
    ) -> Literal["continue", "stop"]:
        desired = self.read()["desired_state"]
        if desired == "stopping":
            self._write_transition("stopping", event="stopping")
            return "stop"
        if desired != "paused":
            return "continue"

        self._write_transition("draining", event="draining")
        self._pause_started = self.clock()
        self._write_transition("paused", event="paused")
        if on_pause:
            on_pause()
        while True:
            desired = self.read()["desired_state"]
            if desired != "paused":
                break
            if on_poll:
                on_poll()
            sleep(poll_seconds)
        if self._pause_started is not None:
            self._paused_total += self.clock() - self._pause_started
            self._pause_started = None
        if desired == "stopping":
            self._write_transition("stopping", event="stopping")
            return "stop"
        self._write_transition("running", event="continued")
        if on_continue:
            on_continue()
        return "continue"

    def finish(self, status: Literal["complete", "interrupted", "failed"]) -> None:
        self._write_transition(status, desired=status, event=status)

    def _write_transition(self, actual: str, *, desired: str | None = None, event: str) -> dict[str, Any]:
        with _record_lock(self.root):
            record = self.read()
            record.update(
                {
                    "actual_state": actual,
                    "desired_state": desired or record["desired_state"],
                    "sequence": int(record.get("sequence", 0)) + 1,
                    "updated_at": _timestamp(),
                    "coordinator_pid": os.getpid(),
                }
            )
            _atomic_json(self.root / "control.json", record)
            self._event(event, record, actor="coordinator")
        return record

    def _event(self, event: str, record: dict[str, Any], *, actor: str) -> None:
        _append_event(
            self.root / "control-events.jsonl",
            {
                "schema_version": 1,
                "event": event,
                "sequence": record["sequence"],
                "timestamp": record["updated_at"],
                "monotonic_seconds": self.clock(),
                "actual_state": record["actual_state"],
                "desired_state": record["desired_state"],
                "actor": actor,
            },
        )


class TerminalControlAdapter:
    """Optional platform key listener; external file commands remain authoritative."""

    def __init__(self, root: str | Path, *, enabled: bool) -> None:
        self.root = Path(root).resolve()
        self.backend = select_terminal_backend(
            os_name=os.name,
            is_tty=enabled and bool(getattr(sys.stdin, "isatty", lambda: False)()),
        )
        self.enabled = self.backend != "none"
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._terminal_state: Any = None

    @property
    def controls_description(self) -> str:
        if self.enabled:
            return "p pause/continue | s graceful stop | Ctrl+C interrupt"
        return "external: run pause|continue|stop OUTPUT_DIR"

    def start(self) -> None:
        if not self.enabled:
            return
        if self.backend == "posix":
            try:
                import termios
                import tty

                descriptor = sys.stdin.fileno()
                self._terminal_state = termios.tcgetattr(descriptor)
                tty.setcbreak(descriptor)
            except Exception:
                self.backend = "none"
                self.enabled = False
                self._terminal_state = None
                return
        self._thread = threading.Thread(target=self._listen, name="run-control-keys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self.backend == "posix" and self._terminal_state is not None:
            try:
                import termios

                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._terminal_state)
            except Exception:
                # Restoration is best-effort during interpreter/terminal teardown;
                # never replace the run's real terminal status with cleanup noise.
                pass
            finally:
                self._terminal_state = None

    def _listen(self) -> None:
        if self.backend == "windows":
            self._listen_windows()
        elif self.backend == "posix":
            self._listen_posix()

    def _handle_key(self, key: str) -> None:
        try:
            if key == "p":
                desired = self._desired_state()
                if desired != "stopping":
                    request_run_action(self.root, "continue" if desired == "paused" else "pause")
            elif key in {"s", "q"}:
                request_run_action(self.root, "stop")
        except (FileNotFoundError, ValueError):
            self._stopped.set()

    def _listen_windows(self) -> None:
        import msvcrt
        while not self._stopped.wait(0.05):
            if not msvcrt.kbhit():
                continue
            self._handle_key(msvcrt.getwch().lower())

    def _listen_posix(self) -> None:
        import select

        while not self._stopped.is_set():
            readable, _, _ = select.select([sys.stdin], [], [], 0.05)
            if readable:
                self._handle_key(sys.stdin.read(1).lower())

    def _desired_state(self) -> str:
        return str(_read(self.root)["desired_state"])


def select_terminal_backend(*, os_name: str | None = None, is_tty: bool | None = None) -> str:
    os_name = os.name if os_name is None else os_name
    is_tty = bool(getattr(sys.stdin, "isatty", lambda: False)()) if is_tty is None else is_tty
    if not is_tty:
        return "none"
    if os_name == "nt":
        return "windows"
    if os_name == "posix":
        return "posix"
    return "none"
