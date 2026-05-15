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

    root = Path(path)
    if dataset_type == "landing":
        names = sorted({landing_class_name(file, root) for file in files})
        class_ids = {name: index for index, name in enumerate(names)}
        assets = [
            Asset(
                file,
                class_ids[landing_class_name(file, root)],
                landing_class_name(file, root),
                foreground_group_name(file, root),
            )
            for file in files
        ]
        return assets, names

    values = sorted({manometro_class_name(file, root) for file in files}, key=manometro_sort_key)
    class_ids = {name: index for index, name in enumerate(values)}
    assets = [
        Asset(file, class_ids[manometro_class_name(file, root)], manometro_class_name(file, root), foreground_group_name(file, root))
        for file in files
    ]
    return assets, values


def manometro_class_name(path: Path, root: Path | None = None) -> str:
    group = foreground_group_name(path, root) if root else None
    if group:
        return group
    match = re.search(r"manometer_(\d+)_(\d+)", path.stem)
    if not match:
        return path.stem
    return f"{match.group(1)}.{match.group(2)}"


def manometro_sort_key(name: str) -> tuple[float, str]:
    range_match = re.match(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$", name)
    if range_match:
        return float(range_match.group(1)), name
    try:
        return float(name), name
    except ValueError:
        return 10**9, name


def landing_class_name(path: Path, root: Path | None = None) -> str:
    stem = path.stem
    group = foreground_group_name(path, root) if root else path.parent.name
    if is_landing_gabarito_group(group):
        parts = stem.split("_")
        if parts and parts[-1].isdigit():
            parts = parts[:-1]
        return "_".join(parts)
    return stem


def foreground_group_name(path: Path, root: Path | None = None) -> str | None:
    if root is None:
        return path.parent.name or None
    try:
        relative = path.relative_to(root)
    except ValueError:
        return path.parent.name or None
    if len(relative.parts) <= 1:
        return None
    return relative.parts[0]


def is_landing_gabarito_group(group: str | None) -> bool:
    if not group:
        return False
    normalized = group.lower()
    return "gabarito" in normalized
