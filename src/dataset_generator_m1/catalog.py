from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .config import _builtin_root, _resolve_reference, load_profile, load_yaml_strict
from .models import GenerationComposer, ProfileBundle, ProfileMetadata


def list_profiles(composer: str | Path | None = None) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for metadata_path in sorted(_builtin_root().glob("*/*/metadata.json")):
        metadata = ProfileMetadata.model_validate(json.loads(metadata_path.read_text(encoding="utf-8")))
        entries.append(metadata.model_dump(mode="json"))
    if composer:
        root = Path(composer).resolve().parent / "profiles" / "workspace"
        for metadata_path in sorted(root.glob("*/*/metadata.json")):
            metadata = ProfileMetadata.model_validate(json.loads(metadata_path.read_text(encoding="utf-8")))
            entries.append(metadata.model_dump(mode="json"))
    return {"schema_version": 1, "status": "complete", "profiles": entries}


def show_profile(reference: str, *, composer: str | Path | None = None) -> dict[str, Any]:
    context = Path(composer).resolve() if composer else Path.cwd() / "composer.yaml"
    path = _resolve_reference(reference, context)
    bundle = ProfileBundle.model_validate(load_yaml_strict(path))
    metadata_path = path.with_name("metadata.json")
    readme_path = path.with_name("README.md")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {
        "schema_version": 1,
        "id": reference,
        "subject": bundle.subject,
        "status": "local",
        "performance_risk": "confirmation",
        "warning_codes": ["UNDOCUMENTED_LOCAL_PROFILE"],
    }
    return {
        "schema_version": 1,
        "status": "complete",
        "reference": reference,
        "path": path.as_posix(),
        "bundle": bundle.model_dump(mode="json"),
        "metadata": metadata,
        "documentation": readme_path.read_text(encoding="utf-8") if readme_path.exists() else None,
    }


def resolved_contract(
    config: str | Path,
    overrides: dict[str, Any] | None = None,
    *,
    override_sources: tuple[Path, ...] = (),
) -> dict[str, Any]:
    resolved = load_profile(config, overrides, override_sources=override_sources)
    return {
        "schema_version": 1,
        "status": "complete",
        "contract_hash": resolved.contract_hash,
        "profile": resolved.profile.model_dump(mode="json"),
        "reference_graph": resolved.reference_graph,
        "source_hashes": resolved.source_hashes,
        "profile_metadata": list(resolved.profile_metadata),
        "applied_overrides": resolved.applied_overrides,
    }


def promote_inline_stack(config: str | Path, stage: str, profile_id: str) -> dict[str, Any]:
    if stage not in {"background", "foreground", "final"}:
        raise ValueError("stage must be background, foreground, or final")
    config_path = Path(config).resolve()
    raw = load_yaml_strict(config_path)
    composer = GenerationComposer.model_validate(raw)
    effects = getattr(composer.appearance.inline, stage)
    if not effects:
        raise ValueError(f"Composer has no inline {stage} effects to promote")
    if "/" in profile_id or "\\" in profile_id or not profile_id:
        raise ValueError("profile ID must be one path-safe name")
    root = config_path.parent / "profiles" / "workspace" / f"appearance.{stage}" / profile_id
    if root.exists():
        raise ValueError(f"Workspace profile already exists: {root}")
    root.mkdir(parents=True)
    bundle = {
        "schema_version": 1,
        "subject": f"appearance.{stage}",
        "value": {"effects": [item.model_dump(mode="json") for item in effects]},
    }
    (root / "profile.yaml").write_text(yaml.safe_dump(bundle, sort_keys=False), encoding="utf-8")
    metadata = {
        "schema_version": 1,
        "id": f"workspace:appearance.{stage}/{profile_id}",
        "subject": f"appearance.{stage}",
        "status": "experimental",
        "compatible_families": ["landing", "manometro"],
        "intents": ["promoted-custom-stack"],
        "performance_risk": "confirmation",
        "warning_codes": ["UNREVIEWED_WORKSPACE_PROFILE"],
    }
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"# {profile_id}\n\nPromoted from `{config_path.name}`. Review visuals, performance, compatibility, and metadata before standard use.\n",
        encoding="utf-8",
    )
    return {"schema_version": 1, "status": "complete", "profile": metadata["id"], "path": root.as_posix()}
