import json
from pathlib import Path

import pytest

from dataset_generator_m1.catalog import list_profiles
from dataset_generator_m1.config import generated_json_schemas, load_appearance_profile, load_profile, load_yaml_strict
from dataset_generator_m1.filters import validate_appearance
from dataset_generator_m1.models import RecipeCatalog, VariantCatalog


def write_recipe(path: Path) -> None:
    path.write_text(
        """\
schema_version: 1
recipes:
  direct:
    nodes:
      - id: source
        op: sample_asset
      - id: canvas
        op: resize_crop
        inputs: {image: source}
    output: canvas
""",
        encoding="utf-8",
    )


def write_bundle(root: Path, subject: str, name: str, value: str) -> Path:
    path = root / subject / name / "profile.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"schema_version: 1\nsubject: {subject}\nvalue:\n{value}", encoding="utf-8")
    return path


def write_profile(path: Path, *, duplicate_family: bool = False) -> None:
    root = path.parent / "profiles"
    family_ref = "profiles/family/landing/profile.yaml"
    family = f"family: {family_ref}\nfamily: {family_ref}" if duplicate_family else f"family: {family_ref}"
    write_bundle(root, "family", "landing", "  family: landing\n")
    write_bundle(root, "run", "run", "  label: contract-test\n  num_images: 2\n  seed: 7\n")
    write_bundle(root, "assets", "assets", "  backgrounds: {paths: [backgrounds]}\n  foregrounds: {paths: [foregrounds/landing_foregrounds]}\n")
    write_bundle(root, "output", "output", "  image_size: [320, 192]\n")
    write_bundle(root, "sampling", "sampling", "  instances_per_image: [1, 2]\n")
    write_bundle(root, "scene", "scene", "  canvas_scale: 2.0\n")
    write_bundle(root, "background_recipes", "background", f"  recipe_file: {path.parent.joinpath('background_recipes.yaml').as_posix()}\n")
    write_bundle(root, "background_mixing", "background", "  recipe_weights: {direct: 1.0}\n")
    write_bundle(root, "appearance", "appearance", "  background: []\n  foreground: []\n  final: []\n")
    write_bundle(root, "execution", "execution", "  workers: 1\n")
    write_bundle(root, "telemetry", "telemetry", "  refresh_hz: 3.0\n")
    write_bundle(root, "reporting", "report", "  qa_samples: 1\n")
    path.write_text(
        f"""schema_version: 2
{family}
run: profiles/run/run/profile.yaml
assets: profiles/assets/assets/profile.yaml
output: profiles/output/output/profile.yaml
sampling: profiles/sampling/sampling/profile.yaml
scene: profiles/scene/scene/profile.yaml
background_recipes: profiles/background_recipes/background/profile.yaml
background_mixing: profiles/background_mixing/background/profile.yaml
appearance:
  preset: profiles/appearance/appearance/profile.yaml
execution: profiles/execution/execution/profile.yaml
telemetry: profiles/telemetry/telemetry/profile.yaml
reporting: profiles/reporting/report/profile.yaml
""",
        encoding="utf-8",
    )


def test_profile_is_strict_and_resolves_family_contract(tmp_path: Path) -> None:
    write_recipe(tmp_path / "background_recipes.yaml")
    profile_path = tmp_path / "profile.yaml"
    write_profile(profile_path)

    resolved = load_profile(profile_path)

    assert resolved.profile.family == "landing"
    assert resolved.profile.output.image_size == (320, 192)
    assert resolved.profile.telemetry.resource_sampling == "continuous"
    assert resolved.family.classes[0] == "estrela_3"
    assert resolved.recipes.recipes["direct"].output == "canvas"


def test_profile_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    write_recipe(tmp_path / "background_recipes.yaml")
    profile_path = tmp_path / "profile.yaml"
    write_profile(profile_path, duplicate_family=True)

    with pytest.raises(ValueError, match="Duplicate YAML key.*family"):
        load_profile(profile_path)


def test_only_declared_operational_overrides_are_accepted(tmp_path: Path) -> None:
    write_recipe(tmp_path / "background_recipes.yaml")
    profile_path = tmp_path / "profile.yaml"
    write_profile(profile_path)

    resolved = load_profile(profile_path, {"num_images": 9, "qa_samples": 2, "execution.workers": 3})

    assert resolved.profile.run.num_images == 9
    assert resolved.profile.report.qa_samples == 2
    assert resolved.profile.execution.workers == 3
    with pytest.raises(ValueError, match="Unknown override path"):
        load_profile(profile_path, {"scene.camera.scale": 0.5})


def test_all_shipped_profiles_recipes_variants_and_schemas_validate() -> None:
    for name in ("landing_minimal.yaml", "manometro_minimal.yaml"):
        load_profile(Path("examples/configs") / name)
    RecipeCatalog.model_validate(load_yaml_strict("examples/configs/background_recipes.yaml"))
    VariantCatalog.model_validate(load_yaml_strict("examples/configs/landing_variants.yaml"))
    schemas = generated_json_schemas()
    assert set(schemas) == {"composer", "resolved-profile", "profile-bundle", "profile-metadata", "family-definition", "background-recipes", "background-catalog", "variants"}
    for name, schema in schemas.items():
        committed = json.loads((Path("docs/schema") / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert committed == schema


def test_all_builtin_appearance_profiles_are_documented_and_executable() -> None:
    expected = {
        "builtin:appearance/realistic-heavy",
        "builtin:appearance/current-fast",
        "builtin:appearance/legacy-heavy-compatible",
        "builtin:appearance/random-fog-heavy",
        "builtin:appearance/no-appearance",
        "builtin:appearance/all-effects-stress",
    }
    catalog = list_profiles()
    appearance_ids = {item["id"] for item in catalog["profiles"] if item["subject"] == "appearance"}
    assert expected <= appearance_ids

    for reference in expected:
        appearance = load_appearance_profile(reference, "examples/configs/landing_minimal.yaml")
        validate_appearance(appearance.background, appearance.foreground, appearance.final)


def test_legacy_profile_now_uses_native_fog_without_rewriting_historical_report() -> None:
    appearance = load_appearance_profile(
        "builtin:appearance/legacy-heavy-compatible",
        "examples/configs/landing_minimal.yaml",
    )
    types = [item.type for item in appearance.final]
    assert "AtmosphericFog" in types
    assert "RandomFog" not in types

    historical = json.loads(Path("docs/experiments/augmentation-heavy-v1/conclusion.json").read_text(encoding="utf-8"))
    assert historical["legacy"]["translation"] == "RandomFog"
    assert historical["legacy"]["fidelity"] == "approximation"
