from __future__ import annotations

import json
from pathlib import Path

from dataset_generator_m1.config import load_profile, load_yaml_strict
from dataset_generator_m1.configurator import add_inline_effect, default_composer, save_composer
from dataset_generator_m1.preflight import (
    PreflightRequest,
    confirm_preflight,
    require_warning_receipt,
    run_preflight,
)


def _composer_with_appearance(tmp_path: Path, preset: str) -> Path:
    raw = load_yaml_strict("examples/configs/landing_minimal.yaml")
    raw["appearance"]["preset"] = preset
    target = tmp_path / "composer.yaml"
    import yaml

    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return target


def test_reviewed_standard_profile_returns_range_without_receipt_or_probe(tmp_path: Path) -> None:
    resolved = load_profile("examples/configs/landing_minimal.yaml", {"num_images": 10})
    called = False

    def probe():
        nonlocal called
        called = True
        return []

    result = run_preflight(
        PreflightRequest(resolved, tmp_path / "run", workers=2, observation_path=tmp_path / "observations.jsonl"),
        probe_runner=probe,
    )

    assert result["status"] == "valid"
    assert result["runtime"]["lower_seconds"] < result["runtime"]["upper_seconds"]
    assert result["runtime"]["confidence"] in {"medium", "high"}
    assert result["required_acknowledgements"] == []
    assert result["probe"]["triggered"] is False
    assert called is False


def test_expensive_profile_runs_bounded_probe_and_requires_bound_receipt(tmp_path: Path) -> None:
    composer = _composer_with_appearance(tmp_path, "builtin:appearance/random-fog-heavy")
    resolved = load_profile(composer, {"num_images": 6})
    calls = 0

    def probe():
        nonlocal calls
        calls += 1
        return [
            {"duration_seconds": 2.0, "accepted": True, "object_count": 1},
            {"duration_seconds": 2.4, "accepted": False, "object_count": 2},
            {"duration_seconds": 2.2, "accepted": True, "object_count": 1},
        ]

    request = PreflightRequest(
        resolved,
        tmp_path / "run",
        workers=1,
        observation_path=tmp_path / "cache" / "observations.jsonl",
    )
    result = run_preflight(request, probe_runner=probe)

    assert calls == 1
    assert result["probe"] == {"triggered": True, "warmups": 1, "measurements": 3}
    assert "RANDOM_FOG_HIGH_COST" in result["required_acknowledgements"]
    observations = (tmp_path / "cache" / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(observations) == 3

    receipt_path = tmp_path / "receipt.json"
    receipt = confirm_preflight(result, receipt_path)
    require_warning_receipt(result, receipt_path)
    assert receipt["binding_hash"] == result["receipt_binding"]["hash"]

    changed = run_preflight(
        PreflightRequest(resolved, tmp_path / "run", workers=2, observation_path=tmp_path / "other.jsonl"),
        probe_runner=lambda: probe(),
    )
    try:
        require_warning_receipt(changed, receipt_path)
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Changing workers must invalidate a warning receipt")


def test_weak_custom_metadata_triggers_probe_but_cache_is_path_isolated(tmp_path: Path) -> None:
    resolved = load_profile("examples/configs/manometro_minimal.yaml").model_copy(
        update={
            "contract_hash": "custom-contract",
            "profile_metadata": (
                {
                    "schema_version": 1,
                    "id": "local:appearance/custom",
                    "subject": "appearance",
                    "status": "local",
                    "performance_risk": "confirmation",
                    "warning_codes": ["UNDOCUMENTED_LOCAL_PROFILE"],
                    "evidence": [],
                },
            ),
        }
    )
    cache = tmp_path / "private-cache" / "observations.jsonl"
    result = run_preflight(
        PreflightRequest(resolved, tmp_path / "run", workers=1, observation_path=cache),
        probe_runner=lambda: [{"duration_seconds": 0.5, "accepted": True, "object_count": 1}] * 3,
    )

    assert result["runtime"]["confidence"] == "local-probe"
    assert cache.exists()
    assert not (tmp_path / "observations.jsonl").exists()
    assert json.loads(cache.read_text(encoding="utf-8").splitlines()[0])["contract_hash"] == "custom-contract"


def test_missing_receipt_is_rejected_only_when_acknowledgements_are_required(tmp_path: Path) -> None:
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    standard = run_preflight(PreflightRequest(resolved, tmp_path / "standard", 1, tmp_path / "obs.jsonl"))
    require_warning_receipt(standard, None)

    risky = dict(standard)
    risky["required_acknowledgements"] = ["TEST_WARNING"]
    try:
        require_warning_receipt(risky, None)
    except ValueError as exc:
        assert "receipt" in str(exc)
    else:
        raise AssertionError("Risky noninteractive generation must require a receipt")


def test_inline_random_fog_requires_cost_acknowledgement(tmp_path: Path) -> None:
    composer = add_inline_effect(
        default_composer("landing"),
        stage="final",
        effect_type="RandomFog",
        effect_id="custom-patch-fog",
        probability=1.0,
        params={},
    )
    path = save_composer(composer, tmp_path / "random-fog.yaml")
    resolved = load_profile(path, {"num_images": 1})

    result = run_preflight(
        PreflightRequest(resolved, tmp_path / "run", 1, tmp_path / "observations.jsonl")
    )

    assert "INLINE_APPEARANCE_UNREVIEWED" in result["required_acknowledgements"]
    assert "RANDOM_FOG_HIGH_COST" in result["required_acknowledgements"]
    assert result["profile"] == "local:appearance/inline-random-fog"
    assert result["runtime"]["confidence"] == "low"
