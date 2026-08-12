from pathlib import Path

import pytest

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.overrides import build_override_plan, parse_set_override


def test_override_precedence_and_source_hash(tmp_path: Path) -> None:
    path = tmp_path / "overrides.yaml"
    path.write_text("run:\n  num_images: 10\nexecution:\n  workers: 2\n", encoding="utf-8")
    plan = build_override_plan(
        override_file=path,
        common={"run.num_images": 20, "execution.workers": 3},
        set_values=("run.num_images=30", "execution.workers=4", "run.num_images=40"),
    )

    resolved = load_profile(
        "examples/configs/landing_minimal.yaml",
        plan.values,
        override_sources=plan.source_paths,
    )

    assert resolved.profile.run.num_images == 40
    assert resolved.profile.execution.workers == 4
    assert path.resolve().as_posix() in resolved.source_hashes


@pytest.mark.parametrize("expression", ["missing-equals", ".run=1", "run.=1", "run..seed=1"])
def test_invalid_set_syntax_fails(expression: str) -> None:
    with pytest.raises(ValueError, match="path=value"):
        parse_set_override(expression)


def test_set_mapping_is_rejected_because_it_is_not_a_leaf() -> None:
    with pytest.raises(ValueError, match="one typed leaf"):
        parse_set_override("run={num_images: 2}")


def test_yaml_11_boolean_words_remain_string_enum_values() -> None:
    assert parse_set_override("telemetry.resource_sampling=off") == (
        "telemetry.resource_sampling",
        "off",
    )
    assert parse_set_override("appearance.enabled=false") == ("appearance.enabled", False)


def test_unknown_or_wrongly_typed_override_fails_during_resolution() -> None:
    with pytest.raises(ValueError, match="Unknown override path"):
        load_profile("examples/configs/landing_minimal.yaml", {"execution.threads": 2})
    with pytest.raises(ValueError):
        load_profile("examples/configs/landing_minimal.yaml", {"execution.workers": "many"})
