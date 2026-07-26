from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dataset_generator_m1.config import load_profile, load_yaml_strict


def write_derived_composer(tmp_path: Path, family: str, changes: dict[str, dict[str, Any]]) -> Path:
    source = Path(f"examples/configs/{family}_minimal.yaml")
    raw = load_yaml_strict(source)
    resolved = load_profile(source)
    for subject, update in changes.items():
        if subject == "background_mixing":
            current = {"recipe_weights": dict(resolved.profile.background_synthesis.recipe_weights)}
        elif subject == "background_recipes":
            current = {"recipe_file": resolved.profile.background_synthesis.recipe_file}
        elif subject == "reporting":
            current = resolved.profile.report.model_dump(mode="json")
        else:
            current = getattr(resolved.profile, subject).model_dump(mode="json")
        current.update(update)
        bundle = tmp_path / "profiles" / subject / "derived" / "profile.yaml"
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(
            yaml.safe_dump({"schema_version": 1, "subject": subject, "value": current}, sort_keys=False),
            encoding="utf-8",
        )
        raw[subject] = bundle.relative_to(tmp_path).as_posix()
    target = tmp_path / "composer.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return target
