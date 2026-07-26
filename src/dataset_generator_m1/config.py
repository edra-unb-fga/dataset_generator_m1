from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .filters import validate_appearance
from .models import BackgroundCatalogMetadata, FamilyDefinition, GenerationProfile, RecipeCatalog, ResolvedProfile, VariantCatalog


class DuplicateKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: DuplicateKeySafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate YAML key at line {key_node.start_mark.line + 1}: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


DuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_yaml_strict(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            loaded = yaml.load(handle, Loader=DuplicateKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {source}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML document must be a mapping: {source}")
    return loaded


def _family_path(name: str) -> Path:
    return Path(__file__).with_name("family_profiles") / f"{name}.yaml"


def _resolve_reference(value: str, config_path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.exists():
        return cwd_candidate.resolve()
    return (config_path.parent / candidate).resolve()


def _apply_operational_overrides(raw: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(raw)
    for key, value in overrides.items():
        if value is None:
            continue
        if key == "num_images":
            updated.setdefault("run", {})["num_images"] = value
        elif key == "qa_samples":
            updated.setdefault("report", {})["qa_samples"] = value
        elif key == "appearance_preset":
            if value != "realistic-heavy":
                raise ValueError(f"Unsupported appearance preset: {value}")
            definition = load_yaml_strict(Path(__file__).parents[2] / "examples" / "experiments" / "augmentation_study.yaml")
            current = updated.setdefault("appearance", {})
            for stage, specs in definition["realistic_heavy"].items():
                current.setdefault(stage, []).extend(deepcopy(specs))
        else:
            raise ValueError(f"Unsupported operational override: {key}")
    return updated


def load_profile(path: str | Path, overrides: dict[str, Any] | None = None) -> ResolvedProfile:
    config_path = Path(path).resolve()
    raw = _apply_operational_overrides(load_yaml_strict(config_path), overrides or {})
    try:
        profile = GenerationProfile.model_validate(raw)
        validate_appearance(profile.appearance.background, profile.appearance.foreground, profile.appearance.final)
        family = FamilyDefinition.model_validate(load_yaml_strict(_family_path(str(raw.get("family", "")))))
        recipe_path = _resolve_reference(profile.background_synthesis.recipe_file, config_path)
        recipes = RecipeCatalog.model_validate(load_yaml_strict(recipe_path))
    except (ValidationError, FileNotFoundError) as exc:
        raise ValueError(str(exc)) from exc

    unknown_recipes = set(profile.background_synthesis.recipe_weights) - set(recipes.recipes)
    if unknown_recipes:
        raise ValueError(f"Unknown background recipe weights: {sorted(unknown_recipes)}")
    if family.name != profile.family:
        raise ValueError(f"Family definition {family.name} does not match profile family {profile.family}")

    contract = {
        "profile": profile.model_dump(mode="json"),
        "family": family.model_dump(mode="json"),
        "recipes": recipes.model_dump(mode="json"),
    }
    contract_hash = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ResolvedProfile(
        profile=profile,
        family=family,
        recipes=recipes,
        config_path=config_path,
        recipe_path=recipe_path,
        contract_hash=contract_hash,
    )


def generated_json_schema() -> dict[str, Any]:
    return GenerationProfile.model_json_schema()


def generated_json_schemas() -> dict[str, dict[str, Any]]:
    return {
        "profile": GenerationProfile.model_json_schema(),
        "background-recipes": RecipeCatalog.model_json_schema(),
        "background-catalog": BackgroundCatalogMetadata.model_json_schema(),
        "variants": VariantCatalog.model_json_schema(),
    }
