import json
from pathlib import Path

import pytest

from dataset_generator_m1.config import generated_json_schemas, load_profile, load_yaml_strict
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


def write_profile(path: Path, *, duplicate_family: bool = False) -> None:
    family_lines = "family: landing\nfamily: manometro" if duplicate_family else "family: landing"
    path.write_text(
        f"""\
schema_version: 1
{family_lines}
run:
  label: contract-test
  num_images: 2
  seed: 7
assets:
  backgrounds:
    paths: [backgrounds]
  foregrounds:
    paths: [foregrounds/landing_foregrounds]
output:
  image_size: [320, 192]
background_synthesis:
  recipe_file: {path.parent.joinpath('background_recipes.yaml').as_posix()}
  recipe_weights: {{direct: 1.0}}
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

    resolved = load_profile(profile_path, {"num_images": 9, "qa_samples": 2})

    assert resolved.profile.run.num_images == 9
    assert resolved.profile.report.qa_samples == 2
    with pytest.raises(ValueError, match="Unsupported operational override"):
        load_profile(profile_path, {"scene.camera.scale": 0.5})


def test_all_shipped_profiles_recipes_variants_and_schemas_validate() -> None:
    for name in ("landing_minimal.yaml", "manometro_minimal.yaml"):
        load_profile(Path("examples/configs") / name)
    RecipeCatalog.model_validate(load_yaml_strict("examples/configs/background_recipes.yaml"))
    VariantCatalog.model_validate(load_yaml_strict("examples/configs/landing_variants.yaml"))
    schemas = generated_json_schemas()
    assert set(schemas) == {"profile", "background-recipes", "background-catalog", "variants"}
    for name, schema in schemas.items():
        committed = json.loads((Path("docs/schema") / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert committed == schema
