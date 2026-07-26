from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class Asset:
    path: Path
    class_id: int
    class_name: str
    group_name: str | None = None


@dataclass
class ForegroundInstance:
    image: np.ndarray
    visible_bbox: BBox
    asset: Asset
    angle: float
    scale: float = 1.0


@dataclass
class PlacedInstance:
    asset: Asset
    bbox: BBox
    attempts: int
    source_path: str
    sampled: dict[str, Any]


@dataclass
class PerspectiveSample:
    enabled: bool
    params: dict[str, Any]
