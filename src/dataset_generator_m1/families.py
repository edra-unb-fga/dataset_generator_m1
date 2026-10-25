"""Discover installed declarative annotation tasks without executable plugins."""
from pathlib import Path

from .models import FamilyDefinition


def family_names() -> tuple[str, ...]:
    import yaml
    root = Path(__file__).with_name("family_profiles")
    names = []
    for path in sorted(root.glob("*.yaml")):
        family = FamilyDefinition.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if family.name != path.stem:
            raise ValueError(f"Family name must match its definition file: {path.name}")
        names.append(family.name)
    return tuple(names)
