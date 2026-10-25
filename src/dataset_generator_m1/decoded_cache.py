"""Bounded process-local source decode cache. Never stores transformed/random images."""
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

_entries: OrderedDict[tuple, np.ndarray] = OrderedDict()
_limit = 0
_bytes = 0
_hits = 0
_misses = 0


def configure_cache(limit_bytes: int) -> None:
    global _limit, _bytes, _hits, _misses
    _entries.clear()
    _limit, _bytes, _hits, _misses = max(0, limit_bytes), 0, 0, 0


def cache_stats() -> dict[str, int]:
    return {"limit_bytes": _limit, "retained_bytes": _bytes, "hits": _hits, "misses": _misses}


@contextmanager
def cache_scope(limit_bytes: int):
    # Top-level generation owns this scope; don't retain assets after a run finishes.
    previous = _limit
    configure_cache(limit_bytes)
    try:
        yield
    finally:
        configure_cache(previous)


def decode(path: Path, mode: str) -> np.ndarray:
    global _bytes, _hits, _misses
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns, mode)
    if _limit and key in _entries:
        _hits += 1
        _entries.move_to_end(key)
        return _entries[key].copy()
    _misses += 1
    with Image.open(path) as image:
        value = np.array(image.convert(mode))
    if _limit and value.nbytes <= _limit:
        while _entries and _bytes + value.nbytes > _limit:
            _, removed = _entries.popitem(last=False)
            _bytes -= removed.nbytes
        retained = value.copy()
        retained.flags.writeable = False
        _entries[key] = retained
        _bytes += retained.nbytes
    return value
