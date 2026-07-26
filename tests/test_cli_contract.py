import json

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
    for command in ("validate", "preview", "generate", "benchmark", "compare", "export"):
        assert command in output
