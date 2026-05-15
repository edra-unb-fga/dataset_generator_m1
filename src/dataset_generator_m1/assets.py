from __future__ import annotations

import re
from pathlib import Path

from .types import Asset

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def discover_images(paths: str | list[str], recursive: bool = True) -> list[Path]:
    roots = [paths] if isinstance(paths, str) else paths
    found: list[Path] = []
    for item in roots:
        root = Path(item)
        if root.is_file() and root.suffix.lower() in IMAGE_EXTENSIONS:
            found.append(root)
        elif root.is_dir():
            iterator = root.rglob("*") if recursive else root.glob("*")
            found.extend(path for path in iterator if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    return sorted(found)


def discover_foregrounds(path: str, dataset_type: str) -> tuple[list[Asset], list[str]]:
    files = discover_images(path, recursive=True)
    if not files:
        raise FileNotFoundError(f"No foreground images found in {path}")

    if dataset_type == "landing":
        names = sorted({landing_class_name(file) for file in files})
        class_ids = {name: index for index, name in enumerate(names)}
        assets = [Asset(file, class_ids[landing_class_name(file)], landing_class_name(file)) for file in files]
        return assets, names

    values = sorted({manometro_class_name(file) for file in files}, key=manometro_sort_key)
    class_ids = {name: index for index, name in enumerate(values)}
    assets = [Asset(file, class_ids[manometro_class_name(file)], manometro_class_name(file)) for file in files]
    return assets, values


def manometro_class_name(path: Path) -> str:
    match = re.search(r"manometer_(\d+)_(\d+)", path.stem)
    if not match:
        return path.stem
    return f"{match.group(1)}.{match.group(2)}"


def manometro_sort_key(name: str) -> tuple[float, str]:
    try:
        return float(name), name
    except ValueError:
        return 10**9, name


def landing_class_name(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return "_".join(parts)

