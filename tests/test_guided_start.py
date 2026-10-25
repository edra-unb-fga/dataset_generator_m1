from __future__ import annotations

import json

from io import StringIO
from pathlib import Path

from rich.console import Console

from dataset_generator_m1.cli import main
from dataset_generator_m1.guided_start import (
    GuidedSession,
    choose_live_mode,
    discover_composers,
    discover_incomplete_runs,
    profile_help,
    render_results_dashboard,
    run_guided_start,
    suggest_output_dir,
)
from dataset_generator_m1.run_control import select_terminal_backend


def test_guided_state_machine_supports_back_cancel_and_mandatory_confirmation() -> None:
    session = GuidedSession()
    assert session.stage == "readiness"
    for action in ("ready", "select", "edit", "review", "prepared"):
        session = session.advance(action)
    assert session.stage == "confirm"
    assert session.advance("decline").stage == "cancelled"
    running = session.advance("confirm")
    assert running.stage == "running"
    assert running.advance("back").stage == "preflight"


def test_discovery_separates_managed_examples_and_invalid_files(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    examples = tmp_path / "examples" / "configs"
    configs.mkdir(parents=True)
    examples.mkdir(parents=True)
    valid = Path("examples/configs/landing_minimal.yaml").read_text(encoding="utf-8")
    (configs / "mine.yaml").write_text(valid, encoding="utf-8")
    (configs / "broken.yaml").write_text("schema_version: nope\n", encoding="utf-8")
    (examples / "landing.yaml").write_text(valid, encoding="utf-8")

    result = discover_composers(tmp_path)
    assert [item["name"] for item in result["managed"]] == ["mine"]
    assert [item["name"] for item in result["examples"]] == ["landing"]
    assert result["invalid"][0]["name"] == "broken"


def test_output_suggestion_is_collision_free(tmp_path: Path) -> None:
    first = suggest_output_dir(tmp_path, "my composer", timestamp="20260730-120000")
    first.mkdir(parents=True)
    second = suggest_output_dir(tmp_path, "my composer", timestamp="20260730-120000")
    assert first.name == "20260730-120000"
    assert second.name == "20260730-120000-02"


def test_incomplete_run_discovery_resolves_a_resumable_managed_composer(tmp_path: Path) -> None:
    config = tmp_path / "configs" / "landing.yaml"
    config.parent.mkdir()
    config.write_text(Path("examples/configs/landing_minimal.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    run = tmp_path / "outputs" / "runs" / "landing" / "incomplete"
    run.mkdir(parents=True)
    (run / "control.json").write_text('{"actual_state":"interrupted"}', encoding="utf-8")
    from dataset_generator_m1.config import load_profile
    (run / "run.json").write_text(json.dumps({"invocation": ["start", "--config", "landing.yaml"], "contract_hash": load_profile(config).contract_hash}), encoding="utf-8")

    discovered = discover_incomplete_runs(tmp_path)

    assert discovered[0]["resumable"] is True
    assert discovered[0]["config_path"] == config


def test_non_tty_start_refuses_with_atomic_command_guidance(capsys) -> None:
    assert main(["start"]) == 1
    output = capsys.readouterr()
    text = output.out + output.err
    assert "configure" in text
    assert "preflight" in text
    assert "generate" in text


def test_profile_help_is_file_backed_and_layout_adapts() -> None:
    help_text = profile_help("builtin:appearance/realistic-heavy")
    assert "realistic heavy appearance" in help_text.lower()
    assert choose_live_mode(True, 120, 35) == "full"
    assert choose_live_mode(True, 80, 24) == "live"
    assert choose_live_mode(False, 120, 35) == "plain"


def test_guided_staged_edit_decline_preserves_original(tmp_path):
    from dataset_generator_m1.guided_start import _edit_composer, GuidedCancelled
    import pytest
    config = tmp_path / "composer.yaml"
    original = Path("examples/configs/landing_minimal.yaml").read_bytes()
    config.write_bytes(original)
    answers = iter(["bad", "0", "2", "42", "1", "192", "128", str(tmp_path / "pool")])
    confirmations = iter([True, False, False])
    console = Console(file=StringIO())
    with pytest.raises(GuidedCancelled):
        _edit_composer(config, tmp_path / "pool", console, lambda *a, **kw: next(answers), lambda *a, **kw: next(confirmations))
    assert config.read_bytes() == original
    assert "Staged changes" in console.file.getvalue()


def test_copy_composer_keeps_relative_profile_meaning(tmp_path):
    from dataset_generator_m1.configurator import copy_composer
    from dataset_generator_m1.config import load_profile
    import yaml
    source = tmp_path / "source" / "composer.yaml"
    source.parent.mkdir()
    raw = yaml.safe_load(Path("examples/configs/landing_minimal.yaml").read_text())
    raw["execution"] = "execution.yaml"
    (source.parent / "execution.yaml").write_text("schema_version: 1\nsubject: execution\nvalue: {workers: 2}\n")
    source.write_text(yaml.safe_dump(raw))
    copied = copy_composer(source, tmp_path / "different" / "composer.yaml")
    assert load_profile(copied).profile.execution.workers == 2


def test_copy_composer_handles_different_windows_volumes(tmp_path, monkeypatch):
    from dataset_generator_m1.configurator import copy_composer
    from dataset_generator_m1.config import load_profile, load_yaml_strict
    source = Path("examples/configs/landing_minimal.yaml")
    def different_mount(*_args):
        raise ValueError("path is on a different mount")
    monkeypatch.setattr("dataset_generator_m1.configurator.os.path.relpath", different_mount)
    copied = copy_composer(source, tmp_path / "composer.yaml")
    assert Path(load_yaml_strict(copied)["inline"]["background_recipes"]["recipe_file"]).is_absolute()
    assert load_profile(copied).recipes == load_profile(source).recipes


def test_terminal_backend_advertises_only_available_controls() -> None:
    assert select_terminal_backend(os_name="nt", is_tty=True) == "windows"
    assert select_terminal_backend(os_name="posix", is_tty=True) == "posix"
    assert select_terminal_backend(os_name="posix", is_tty=False) == "none"


def test_results_dashboard_keeps_quality_performance_and_audit_separate() -> None:
    console = Console(file=StringIO(), force_terminal=False, width=100)
    console.print(
        render_results_dashboard(
            {
                "status": "complete",
                "accepted_samples": 2,
                "target_samples": 2,
                "pool_path": "outputs/demo",
                "elapsed_seconds": 3.0,
                "paused_seconds": 0.0,
                "throughput_images_per_second": 0.66,
                "performance_observation": {"status": "recorded"},
            },
            {"status": "valid", "findings": []},
        )
    )
    rendered = console.file.getvalue()
    assert "Quality and QA" in rendered
    assert "Performance" in rendered
    assert "Audit evidence" in rendered


def test_guided_journey_saves_prepares_generates_and_inspects(tmp_path: Path, monkeypatch) -> None:
    examples = tmp_path / "examples" / "configs"
    examples.mkdir(parents=True)
    source = Path("examples/configs/landing_minimal.yaml")
    config = examples / source.name
    config.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    output = tmp_path / "guided-output"
    answers = iter(["continue", "1", "42", "1", "192", "128", str(output), "prepare", "exit"])
    confirmations = iter([True, False, True, True])

    class _TTY:
        @staticmethod
        def isatty() -> bool:
            return True

    monkeypatch.setattr("dataset_generator_m1.guided_start.sys.stdin", _TTY())
    console = Console(file=StringIO(), force_terminal=True, width=100)
    result = run_guided_start(
        config,
        root=tmp_path,
        console=console,
        ask=lambda *_args, **_kwargs: next(answers),
        confirm=lambda *_args, **_kwargs: next(confirmations),
        interactive=True,
    )

    assert result["status"] == "complete"
    assert result["inspection"]["status"] == "valid"
    assert Path(result["config"]).parent == tmp_path / "configs"
    assert (output / "summary.json").is_file()
