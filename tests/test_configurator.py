import json
from pathlib import Path

from dataset_generator_m1.cli import main
from dataset_generator_m1.catalog import list_profiles, promote_inline_stack
from dataset_generator_m1.config import load_yaml_strict
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.configurator import (
    add_inline_effect,
    default_composer,
    effect_catalog,
    save_composer,
    set_inline_values,
    set_subject_reference,
)
from dataset_generator_m1.filters import SUPPORTED_TRANSFORMS


def test_noninteractive_configure_saves_realistic_heavy_composer(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "landing.yaml"

    exit_code = main(
        [
            "configure",
            "--family",
            "landing",
            "--output",
            str(destination),
            "--run-output-dir",
            str(tmp_path / "pool"),
            "--output-format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    resolved = load_profile(destination)
    assert exit_code == 0
    assert payload["appearance"] == "builtin:appearance/realistic-heavy"
    assert resolved.profile.execution.workers == 1
    assert resolved.reference_graph["appearance"]["preset"]["reference"] == "builtin:appearance/realistic-heavy"


def test_cockpit_inline_values_are_strict_and_resolved(tmp_path: Path) -> None:
    document = default_composer("manometro")
    document = set_inline_values(document, "run", {"num_images": 17, "seed": 91})
    document = set_inline_values(document, "execution", {"workers": "auto"})
    document = set_inline_values(document, "output", {"image_size": [640, 480]})
    destination = save_composer(document, tmp_path / "manometro.yaml")

    resolved = load_profile(destination)
    assert resolved.profile.run.num_images == 17
    assert resolved.profile.execution.workers == "auto"
    assert resolved.profile.output.image_size == (640, 480)
    assert resolved.reference_graph["run"]["inline"] == {"num_images": 17, "seed": 91}


def test_subject_browser_accepts_a_typed_reference_and_rejects_family_replacement() -> None:
    document = set_subject_reference(default_composer("landing"), "execution", "builtin:execution/standard")
    assert document["execution"] == "builtin:execution/standard"
    try:
        set_subject_reference(document, "family", "builtin:family/manometro")
    except ValueError as exc:
        assert "not user-selectable" in str(exc)
    else:
        raise AssertionError("family replacement bypassed guided-family consistency")


def test_every_supported_effect_has_file_backed_guidance() -> None:
    catalog = effect_catalog()
    assert set(catalog["effects"]) == SUPPORTED_TRANSFORMS
    assert Path(catalog["documentation"]).exists()


def test_advanced_builder_adds_native_fog_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    document = add_inline_effect(
        default_composer("landing"),
        stage="final",
        effect_type="AtmosphericFog",
        effect_id="custom-atmospheric",
        probability=0.4,
        params={"depth_mode": "radial", "density_range": [0.2, 0.5]},
    )
    destination = save_composer(document, tmp_path / "fog.yaml")
    resolved = load_profile(destination)
    effect = resolved.profile.appearance.final[-1]
    assert effect.id == "custom-atmospheric"
    assert effect.params["depth_mode"] == "radial"

    try:
        add_inline_effect(
            document,
            stage="final",
            effect_type="GaussianBlur",
            effect_id="custom-atmospheric",
            probability=1.0,
            params={},
        )
    except ValueError as exc:
        assert "Duplicate transform id" in str(exc)
    else:
        raise AssertionError("duplicate effect ID was accepted")


def test_promoting_inline_stack_preserves_resolved_behavior(tmp_path: Path) -> None:
    document = add_inline_effect(
        default_composer("landing"),
        stage="background",
        effect_type="GaussianBlur",
        effect_id="reviewed-blur",
        probability=0.5,
        params={"blur_limit": [3, 5]},
    )
    path = save_composer(document, tmp_path / "composer.yaml")
    before = [item.model_dump(mode="json") for item in load_profile(path).profile.appearance.background]

    promoted = promote_inline_stack(path, "background", "reviewed-blur")
    migrated = load_yaml_strict(path)
    migrated["appearance"]["background"] = [promoted["profile"]]
    migrated["appearance"]["inline"]["background"] = []
    save_composer(migrated, path)

    after = [item.model_dump(mode="json") for item in load_profile(path).profile.appearance.background]
    assert after == before
    assert any(item["id"] == promoted["profile"] for item in list_profiles(path)["profiles"])
