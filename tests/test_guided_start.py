from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from dataset_generator_m1.cli import main
from dataset_generator_m1.guided_start import (
    GuidedSession,
    choose_live_mode,
    discover_composers,
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
    confirmations = iter([True, False, True])

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
    )

    assert result["status"] == "complete"
    assert result["inspection"]["status"] == "valid"
    assert Path(result["config"]).parent == tmp_path / "configs"
    assert (output / "summary.json").is_file()
