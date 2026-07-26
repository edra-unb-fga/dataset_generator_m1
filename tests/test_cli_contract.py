import json
from pathlib import Path

from dataset_generator_m1.cli import main


def test_validate_command_supports_final_json_output(capsys) -> None:
    exit_code = main(
        [
            "validate",
            "--config",
            "examples/configs/landing_minimal.yaml",
            "--display",
            "quiet",
            "--output-format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "valid"
    assert payload["family"] == "landing"
    assert payload["catalog"]["backgrounds"] == 82
    assert payload["recipes"] == ["direct", "displaced", "mask_multiband", "palette"]


def test_cli_exposes_integrated_commands(capsys) -> None:
    exit_code = main(["--help"])

    output = capsys.readouterr().out
    assert exit_code == 0
    for command in ("catalog", "configure", "resolve", "preflight", "validate", "preview", "generate", "run", "experiment", "benchmark", "compare", "export"):
        assert command in output


def test_resolve_accepts_override_file_common_options_and_repeated_sets(tmp_path, capsys) -> None:
    overrides = tmp_path / "run-overrides.yaml"
    overrides.write_text("run:\n  num_images: 7\nexecution:\n  workers: 2\n", encoding="utf-8")
    assert main(
        [
            "resolve",
            "--config",
            "examples/configs/landing_minimal.yaml",
            "--overrides",
            str(overrides),
            "--set",
            "run.num_images=9",
            "--set",
            "run.num_images=11",
            "--output-format",
            "json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"]["run"]["num_images"] == 11
    assert payload["profile"]["execution"]["workers"] == 2
    assert Path(overrides).resolve().as_posix() in payload["source_hashes"]


def test_run_status_command_supports_json(tmp_path, capsys) -> None:
    from dataset_generator_m1.run_control import RunController

    RunController.open(tmp_path, resume=False)
    assert main(["run", "status", str(tmp_path), "--output-format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"
    assert payload["actual_state"] == "running"


def test_preflight_command_supports_final_json_output(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "preflight",
            "--config",
            "examples/configs/landing_minimal.yaml",
            "--output-dir",
            str(tmp_path / "pool"),
            "--output-format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "valid"
    assert payload["runtime"]["upper_seconds"] > payload["runtime"]["lower_seconds"]
    assert payload["required_acknowledgements"] == []


def test_catalog_and_resolve_expose_profile_provenance(capsys) -> None:
    assert main(["catalog", "list", "--output-format", "json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert any(item["id"] == "builtin:appearance/realistic-heavy" for item in listing["profiles"])

    assert main(["resolve", "--config", "examples/configs/landing_minimal.yaml", "--output-format", "json"]) == 0
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["profile"]["schema_version"] == 2
    assert resolved["reference_graph"]["appearance"]["preset"]["reference"] == "builtin:appearance/realistic-heavy"


def test_realistic_heavy_is_the_shipped_default() -> None:
    from dataset_generator_m1.config import load_profile

    default = load_profile("examples/configs/landing_minimal.yaml")
    metadata_ids = {item["id"] for item in default.profile_metadata}

    assert "builtin:appearance/realistic-heavy" in metadata_ids
    assert any(spec.id == "realistic-final-weather" for spec in default.profile.appearance.final)
