from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from .config import load_yaml_strict
from .models import BackgroundCatalogMetadata, ResolvedProfile
from .types import Asset

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_IMAGE_CACHE: dict[tuple[str, int, int], tuple[int, int, str, str]] = {}


@dataclass(frozen=True)
class AssetRecord:
    path: Path
    logical_path: str
    content_hash: str
    perceptual_hash: str
    group: str
    width: int
    height: int
    mode: str
    class_id: int | None = None
    class_name: str | None = None
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    seamless: bool | None = None
    texture_kind: str | None = None
    approved_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogQuality:
    exact_duplicate_groups: tuple[tuple[str, ...], ...]
    perceptual_duplicate_groups: tuple[tuple[str, ...], ...]
    background_group_counts: dict[str, int]
    foreground_group_counts: dict[str, int]
    class_counts: dict[str, int]


@dataclass(frozen=True)
class AssetCatalog:
    backgrounds: tuple[AssetRecord, ...]
    foregrounds: tuple[AssetRecord, ...]
    class_names: tuple[str, ...]
    fingerprint: str
    quality: CatalogQuality


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


def _resolve_roots(paths: Iterable[str]) -> list[Path]:
    roots: list[Path] = []
    for value in paths:
        path = Path(value)
        roots.append(path.resolve())
    return roots


def _discover_records(roots: list[Path], recursive: bool) -> list[tuple[Path, Path, str]]:
    found: list[tuple[Path, Path, str]] = []
    for root_index, root in enumerate(roots):
        if root.is_file() and root.suffix.lower() in IMAGE_EXTENSIONS:
            found.append((root, root.parent, f"root{root_index}/{root.name}"))
            continue
        if not root.is_dir():
            raise FileNotFoundError(f"Asset root does not exist: {root}")
        iterator = root.rglob("*") if recursive else root.glob("*")
        for path in iterator:
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                relative = path.relative_to(root).as_posix()
                found.append((path.resolve(), root, f"root{root_index}/{relative}"))
    return sorted(found, key=lambda item: item[2])


def _hash_file(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _HASH_CACHE[key] = value
    return value


def _inspect_image(path: Path) -> tuple[int, int, str, str]:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            mode = image.mode
            gray = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            values = np.asarray(gray, dtype=np.float32)
            bits = (values >= values.mean()).reshape(-1)
            perceptual = f"{int(''.join('1' if bit else '0' for bit in bits), 2):016x}"
    except Exception as exc:
        raise ValueError(f"Could not decode asset {path}: {exc}") from exc
    value = (width, height, mode, perceptual)
    _IMAGE_CACHE[key] = value
    return value


def _group_for(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    return relative.parts[0] if len(relative.parts) > 1 else root.name


def _load_background_metadata(resolved: ResolvedProfile) -> dict[str, object]:
    source = resolved.profile.assets.backgrounds
    if not source.catalog_file:
        return {}
    path = Path(source.catalog_file)
    if not path.is_absolute():
        cwd_candidate = Path.cwd() / path
        path = cwd_candidate if cwd_candidate.exists() else resolved.config_path.parent / path
    metadata = BackgroundCatalogMetadata.model_validate(load_yaml_strict(path))
    return {entry.path.replace("\\", "/"): entry for entry in metadata.assets}


def _map_foreground(relative_stem: str, resolved: ResolvedProfile) -> tuple[int, str]:
    matches: list[str] = []
    for rule in resolved.family.class_mapping:
        match = re.fullmatch(rule.pattern, relative_stem)
        if match:
            matches.append(rule.class_template.format(**match.groupdict()))
    if len(matches) != 1:
        raise ValueError(f"Foreground {relative_stem} must match exactly one class rule; matched {matches}")
    class_name = matches[0]
    if class_name not in resolved.family.classes:
        raise ValueError(f"Foreground {relative_stem} mapped to undeclared class {class_name}")
    return resolved.family.classes.index(class_name), class_name


def _duplicate_groups(records: tuple[AssetRecord, ...], field: str) -> tuple[tuple[str, ...], ...]:
    grouped: dict[str, list[str]] = {}
    for record in records:
        grouped.setdefault(str(getattr(record, field)), []).append(record.logical_path)
    return tuple(tuple(paths) for paths in grouped.values() if len(paths) > 1)


def _counts(records: tuple[AssetRecord, ...], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in records:
        value = getattr(record, field)
        if value is not None:
            result[str(value)] = result.get(str(value), 0) + 1
    return result


def _validate_weight_keys(records: tuple[AssetRecord, ...], source: object, label: str) -> None:
    groups = {record.group for record in records}
    logical_paths = {record.logical_path for record in records}
    unknown_groups = set(getattr(source, "group_weights")) - groups
    unknown_assets = set(getattr(source, "asset_weights")) - logical_paths
    if unknown_groups:
        raise ValueError(f"Unknown {label} groups in weights: {sorted(unknown_groups)}")
    if unknown_assets:
        raise ValueError(f"Unknown {label} assets in weights: {sorted(unknown_assets)}")


def build_asset_catalog(resolved: ResolvedProfile) -> AssetCatalog:
    background_source = resolved.profile.assets.backgrounds
    foreground_source = resolved.profile.assets.foregrounds
    background_roots = _resolve_roots(background_source.paths)
    foreground_roots = _resolve_roots(foreground_source.paths)
    background_metadata = _load_background_metadata(resolved)

    backgrounds: list[AssetRecord] = []
    for path, root, logical_path in _discover_records(background_roots, background_source.recursive):
        relative = path.relative_to(root).as_posix()
        meta = background_metadata.get(relative)
        if meta is not None and getattr(meta, "excluded", False):
            continue
        width, height, mode, perceptual = _inspect_image(path)
        backgrounds.append(
            AssetRecord(
                path=path,
                logical_path=logical_path,
                content_hash=_hash_file(path),
                perceptual_hash=perceptual,
                group=_group_for(path, root),
                width=width,
                height=height,
                mode=mode,
                tags=tuple(getattr(meta, "tags", ())) if meta else (),
                aliases=tuple(getattr(meta, "aliases", ())) if meta else (),
                seamless=getattr(meta, "seamless", None) if meta else None,
                texture_kind=getattr(meta, "texture_kind", None) if meta else None,
                approved_roles=tuple(getattr(meta, "approved_roles", ())) if meta else (),
            )
        )

    foregrounds: list[AssetRecord] = []
    for path, root, logical_path in _discover_records(foreground_roots, foreground_source.recursive):
        relative_stem = path.relative_to(root).with_suffix("").as_posix()
        class_id, class_name = _map_foreground(relative_stem, resolved)
        width, height, mode, perceptual = _inspect_image(path)
        foregrounds.append(
            AssetRecord(
                path=path,
                logical_path=logical_path,
                content_hash=_hash_file(path),
                perceptual_hash=perceptual,
                group=_group_for(path, root),
                width=width,
                height=height,
                mode=mode,
                class_id=class_id,
                class_name=class_name,
            )
        )

    if not backgrounds:
        raise ValueError("Background catalog is empty")
    if not foregrounds:
        raise ValueError("Foreground catalog is empty")
    _validate_weight_keys(tuple(backgrounds), background_source, "background")
    _validate_weight_keys(tuple(foregrounds), foreground_source, "foreground")
    class_counts = _counts(tuple(foregrounds), "class_name")
    missing_classes = set(resolved.family.classes) - set(class_counts)
    if missing_classes:
        raise ValueError(f"Declared classes without assets: {sorted(missing_classes)}")

    all_records = tuple(backgrounds + foregrounds)
    fingerprint_payload = [
        {
            "logical_path": record.logical_path,
            "content_hash": record.content_hash,
            "group": record.group,
            "class_name": record.class_name,
            "tags": record.tags,
        }
        for record in all_records
    ]
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")).hexdigest()
    quality = CatalogQuality(
        exact_duplicate_groups=_duplicate_groups(all_records, "content_hash"),
        perceptual_duplicate_groups=_duplicate_groups(all_records, "perceptual_hash"),
        background_group_counts=_counts(tuple(backgrounds), "group"),
        foreground_group_counts=_counts(tuple(foregrounds), "group"),
        class_counts=class_counts,
    )
    return AssetCatalog(
        backgrounds=tuple(backgrounds),
        foregrounds=tuple(foregrounds),
        class_names=resolved.family.classes,
        fingerprint=fingerprint,
        quality=quality,
    )


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
