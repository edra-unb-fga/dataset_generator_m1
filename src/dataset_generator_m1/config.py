from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .filters import validate_appearance
from .models import (
    AppearanceConfig,
    BackgroundCatalogMetadata,
    FamilyDefinition,
    GenerationComposer,
    GenerationProfile,
    ProfileBundle,
    ProfileMetadata,
    RecipeCatalog,
    ResolvedProfile,
    VariantCatalog,
)


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


DuplicateKeySafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _family_path(name: str) -> Path:
    return Path(__file__).with_name("family_profiles") / f"{name}.yaml"


def _builtin_root() -> Path:
    return Path(__file__).with_name("profiles") / "builtin"


def _resolve_reference(value: str, config_path: Path, expected_subject: str | None = None) -> Path:
    if value.startswith("builtin:"):
        identity = value.removeprefix("builtin:")
        subject, separator, name = identity.partition("/")
        if not separator or not name:
            raise ValueError(f"Invalid built-in profile ID: {value}")
        if expected_subject and subject != expected_subject:
            raise ValueError(f"Profile {value} cannot fill subject {expected_subject}")
        return (_builtin_root() / subject / name / "profile.yaml").resolve()
    if value.startswith("workspace:"):
        identity = value.removeprefix("workspace:")
        subject, separator, name = identity.partition("/")
        if not separator or not name:
            raise ValueError(f"Invalid workspace profile ID: {value}")
        if expected_subject and subject != expected_subject:
            raise ValueError(f"Profile {value} cannot fill subject {expected_subject}")
        return (config_path.parent / "profiles" / "workspace" / subject / name / "profile.yaml").resolve()
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.exists():
        return cwd_candidate.resolve()
    return (config_path.parent / candidate).resolve()


def _merge_bundle_value(subject: str, base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    if subject == "appearance":
        result = {stage: list(base.get(stage, ())) for stage in ("background", "foreground", "final")}
        for stage in result:
            result[stage].extend(deepcopy(extra.get(stage, ())))
        unknown = set(extra) - set(result)
        if unknown:
            raise ValueError(f"Appearance profile has unknown stages: {sorted(unknown)}")
        return result
    if base:
        overlap = set(base) & set(extra)
        if overlap:
            raise ValueError(f"Profile extension for {subject} would override fields {sorted(overlap)}; use a complete profile")
    return {**base, **deepcopy(extra)}


def _load_bundle(
    reference: str,
    composer_path: Path,
    subject: str,
    *,
    stack: tuple[Path, ...] = (),
) -> tuple[dict[str, Any], list[Path], list[dict[str, Any]], dict[str, Any]]:
    path = _resolve_reference(reference, composer_path, subject if reference.startswith(("builtin:", "workspace:")) else None)
    if path in stack:
        cycle = " -> ".join(item.as_posix() for item in (*stack, path))
        raise ValueError(f"Profile reference cycle: {cycle}")
    if not path.exists():
        raise ValueError(f"Profile reference does not exist: {reference} -> {path}")
    try:
        bundle = ProfileBundle.model_validate(load_yaml_strict(path))
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    if bundle.subject != subject:
        raise ValueError(f"Profile {reference} declares subject {bundle.subject}, expected {subject}")
    value: dict[str, Any] = {}
    sources: list[Path] = []
    metadata: list[dict[str, Any]] = []
    graph: dict[str, Any] = {"reference": reference, "path": path.as_posix(), "extends": list(bundle.extends)}
    for parent in bundle.extends:
        parent_value, parent_sources, parent_metadata, _ = _load_bundle(parent, composer_path, subject, stack=(*stack, path))
        value = _merge_bundle_value(subject, value, parent_value)
        sources.extend(parent_sources)
        metadata.extend(parent_metadata)
    value = _merge_bundle_value(subject, value, bundle.value)
    sources.append(path)
    metadata_path = path.with_name("metadata.json")
    readme_path = path.with_name("README.md")
    if reference.startswith("builtin:"):
        if not metadata_path.exists() or not readme_path.exists():
            raise ValueError(f"Built-in profile bundle is incomplete: {path.parent}")
    if metadata_path.exists():
        try:
            parsed = ProfileMetadata.model_validate(json.loads(metadata_path.read_text(encoding="utf-8")))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid profile metadata {metadata_path}: {exc}") from exc
        if parsed.subject != subject:
            raise ValueError(f"Metadata subject {parsed.subject} does not match {subject}: {metadata_path}")
        metadata.append(parsed.model_dump(mode="json"))
        sources.append(metadata_path)
    else:
        metadata.append({"schema_version": 1, "id": reference, "subject": subject, "status": "local", "performance_risk": "confirmation", "warning_codes": ["UNDOCUMENTED_LOCAL_PROFILE"]})
    if readme_path.exists():
        sources.append(readme_path)
    return value, sources, metadata, graph


def _set_leaf(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node: Any = target
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"Unknown override path: {path}")
        node = node[part]
    if not isinstance(node, dict) or parts[-1] not in node:
        raise ValueError(f"Unknown override path: {path}")
    node[parts[-1]] = value


def _normalized_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in overrides.items():
        if value is None:
            continue
        aliases = {"num_images": "run.num_images", "qa_samples": "report.qa_samples"}
        if key == "appearance_preset":
            raise ValueError("--appearance-preset was replaced by composer appearance profiles")
        result[aliases.get(key, key)] = value
    return result


def _merge_inline(base: dict[str, Any], inline: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in inline.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_inline(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_profile(
    path: str | Path,
    overrides: dict[str, Any] | None = None,
    *,
    override_sources: tuple[Path, ...] = (),
) -> ResolvedProfile:
    config_path = Path(path).resolve()
    raw = load_yaml_strict(config_path)
    if raw.get("schema_version") != 2:
        raise ValueError("Generation requires composer schema_version 2; v1 pools remain available to audit, compare, and export")
    try:
        composer = GenerationComposer.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    references = {
        "family": composer.family,
        "run": composer.run,
        "assets": composer.assets,
        "output": composer.output,
        "sampling": composer.sampling,
        "scene": composer.scene,
        "execution": composer.execution,
        "telemetry": composer.telemetry,
    }
    resolved_values: dict[str, Any] = {"schema_version": 2}
    sources: list[Path] = [config_path, *override_sources]
    metadata: list[dict[str, Any]] = []
    graph: dict[str, Any] = {}
    for subject, reference in references.items():
        value, found_sources, found_metadata, node = _load_bundle(reference, config_path, subject)
        inline_model = getattr(composer.inline, subject, None)
        if inline_model is not None:
            value = _merge_inline(value, inline_model.model_dump(mode="json", exclude_none=True))
            node["inline"] = inline_model.model_dump(mode="json", exclude_none=True)
        resolved_values[subject] = value["family"] if subject == "family" else value
        sources.extend(found_sources)
        metadata.extend(found_metadata)
        graph[subject] = node

    background_value: dict[str, Any] = {}
    for subject, reference in (
        ("background_recipes", composer.background_recipes),
        ("background_mixing", composer.background_mixing),
    ):
        value, found_sources, found_metadata, node = _load_bundle(reference, config_path, subject)
        inline_model = getattr(composer.inline, subject)
        if inline_model is not None:
            value = _merge_inline(value, inline_model.model_dump(mode="json", exclude_none=True))
            node["inline"] = inline_model.model_dump(mode="json", exclude_none=True)
        background_value.update(value)
        sources.extend(found_sources)
        metadata.extend(found_metadata)
        graph[subject] = node
    resolved_values["background_synthesis"] = background_value

    report_value, report_sources, report_metadata, report_node = _load_bundle(
        composer.reporting, config_path, "reporting"
    )
    if composer.inline.reporting is not None:
        inline_report = composer.inline.reporting.model_dump(mode="json", exclude_none=True)
        report_value = _merge_inline(report_value, inline_report)
        report_node["inline"] = inline_report
    resolved_values["report"] = report_value
    sources.extend(report_sources)
    metadata.extend(report_metadata)
    graph["reporting"] = report_node

    appearance_value, appearance_sources, appearance_metadata, appearance_node = _load_bundle(composer.appearance.preset, config_path, "appearance")
    sources.extend(appearance_sources)
    metadata.extend(appearance_metadata)
    graph["appearance"] = {
        "preset": appearance_node,
        "stages": {},
        "inline": composer.appearance.inline.model_dump(mode="json"),
    }
    for stage in ("background", "foreground", "final"):
        for reference in getattr(composer.appearance, stage):
            value, found_sources, found_metadata, node = _load_bundle(reference, config_path, f"appearance.{stage}")
            appearance_value[stage] = [*appearance_value.get(stage, ()), *value.get("effects", ())]
            sources.extend(found_sources)
            metadata.extend(found_metadata)
            graph["appearance"]["stages"].setdefault(stage, []).append(node)
        appearance_value[stage] = [*appearance_value.get(stage, ()), *[item.model_dump(mode="json") for item in getattr(composer.appearance.inline, stage)]]
    resolved_values["appearance"] = appearance_value

    applied = _normalized_overrides(overrides or {})
    for override_path, value in applied.items():
        _set_leaf(resolved_values, override_path, value)

    try:
        profile = GenerationProfile.model_validate(resolved_values)
        validate_appearance(profile.appearance.background, profile.appearance.foreground, profile.appearance.final)
        family = FamilyDefinition.model_validate(load_yaml_strict(_family_path(profile.family)))
        recipe_path = _resolve_reference(profile.background_synthesis.recipe_file, config_path)
        recipes = RecipeCatalog.model_validate(load_yaml_strict(recipe_path))
    except (ValidationError, FileNotFoundError) as exc:
        raise ValueError(str(exc)) from exc
    if family.name != profile.family:
        raise ValueError(f"Family definition {family.name} does not match profile family {profile.family}")
    unknown_recipes = set(profile.background_synthesis.recipe_weights) - set(recipes.recipes)
    if unknown_recipes:
        raise ValueError(f"Unknown background recipe weights: {sorted(unknown_recipes)}")
    sources.extend([_family_path(profile.family), recipe_path])
    unique_sources = list(dict.fromkeys(item.resolve() for item in sources))
    source_hashes = {item.as_posix(): _sha256(item) for item in unique_sources}
    contract = {
        "profile": profile.model_dump(mode="json"),
        "family": family.model_dump(mode="json"),
        "recipes": recipes.model_dump(mode="json"),
        "source_hashes": source_hashes,
        "reference_graph": graph,
        "applied_overrides": applied,
    }
    contract_hash = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ResolvedProfile(
        profile=profile,
        family=family,
        recipes=recipes,
        config_path=config_path,
        recipe_path=recipe_path,
        contract_hash=contract_hash,
        source_hashes=source_hashes,
        reference_graph=graph,
        profile_metadata=tuple(metadata),
        applied_overrides=applied,
    )


def load_appearance_profile(reference: str, composer_path: str | Path) -> AppearanceConfig:
    """Resolve one named/path appearance profile through the same catalog seam as generation."""
    value, _, _, _ = _load_bundle(reference, Path(composer_path).resolve(), "appearance")
    try:
        appearance = AppearanceConfig.model_validate(value)
        validate_appearance(appearance.background, appearance.foreground, appearance.final)
        return appearance
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def generated_json_schema() -> dict[str, Any]:
    return GenerationComposer.model_json_schema()


def generated_json_schemas() -> dict[str, dict[str, Any]]:
    return {
        "composer": GenerationComposer.model_json_schema(),
        "resolved-profile": GenerationProfile.model_json_schema(),
        "profile-bundle": ProfileBundle.model_json_schema(),
        "profile-metadata": ProfileMetadata.model_json_schema(),
        "family-definition": FamilyDefinition.model_json_schema(),
        "background-recipes": RecipeCatalog.model_json_schema(),
        "background-catalog": BackgroundCatalogMetadata.model_json_schema(),
        "variants": VariantCatalog.model_json_schema(),
    }
