from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import load_yaml_strict


@dataclass(frozen=True)
class OverridePlan:
    values: dict[str, Any]
    source_paths: tuple[Path, ...] = ()


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Override keys must be non-empty strings")
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(_flatten(item, path))
        else:
            result[path] = item
    return result


def parse_set_override(expression: str) -> tuple[str, Any]:
    path, separator, raw = expression.partition("=")
    if not separator or not path or path.startswith(".") or path.endswith(".") or ".." in path:
        raise ValueError(f"Typed override must use path=value: {expression}")
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML value in --set {expression}: {exc}") from exc
    if isinstance(value, dict):
        raise ValueError(f"--set targets one typed leaf; mapping value is not allowed: {path}")
    return path, value


def build_override_plan(
    *,
    override_file: str | Path | None = None,
    common: dict[str, Any] | None = None,
    set_values: Iterable[str] = (),
) -> OverridePlan:
    values: dict[str, Any] = {}
    sources: list[Path] = []
    if override_file:
        source = Path(override_file).resolve()
        values.update(_flatten(load_yaml_strict(source)))
        sources.append(source)
    values.update({key: value for key, value in (common or {}).items() if value is not None})
    for expression in set_values:
        path, value = parse_set_override(expression)
        values[path] = value
    return OverridePlan(values, tuple(sources))
