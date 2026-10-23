"""Lifetime ownership for a local generation coordinator.

The lock file persists: unlinking an open lock would let a second inode acquire
ownership. OS locks, rather than PID files, decide whether a writer is active.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import BinaryIO

import psutil


class CoordinatorLease:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.handle: BinaryIO | None = None

    def __enter__(self) -> "CoordinatorLease":
        self.root.mkdir(parents=True, exist_ok=True)
        handle = os.fdopen(os.open(self.root / "coordinator.lock", os.O_RDWR | os.O_CREAT, 0o600), "r+b")
        try:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b" ")
                handle.flush()
            self._lock(handle)
        except OSError as exc:
            handle.close()
            raise RuntimeError("An active coordinator owns this pool; use run status/pause/continue/stop, not resume") from exc
        self.handle = handle
        try:
            owner = {"pid": os.getpid(), "process_created": psutil.Process().create_time()}
            handle.seek(1)
            handle.write(json.dumps(owner).encode("utf-8"))
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            self.close()
            raise
        return self

    @staticmethod
    def _lock(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def __exit__(self, *_args: object) -> None:
        self.close()


def coordinator_ownership(root: str | Path) -> dict[str, object]:
    """Read ownership without changing the pool or trusting a possibly reused PID."""
    path = Path(root) / "coordinator.lock"
    if not path.exists():
        return {"state": "unrecorded"}
    try:
        with path.open("r+b") as handle:
            try:
                CoordinatorLease._lock(handle)
            except OSError:
                return {"state": "active"}
            handle.seek(1)
            try:
                owner = json.loads(handle.read().decode("utf-8"))
            except (ValueError, UnicodeError):
                return {"state": "uncertain", "reason": "invalid ownership metadata"}
            if not isinstance(owner, dict) or not isinstance(owner.get("pid"), int) or not isinstance(owner.get("process_created"), (int, float)):
                return {"state": "uncertain", "reason": "invalid process identity"}
            return {"state": "inactive", "previous_owner": owner}
    except OSError:
        return {"state": "uncertain", "reason": "ownership record inaccessible"}
