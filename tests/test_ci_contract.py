from pathlib import Path
import tomllib
import yaml


ROOT = Path(__file__).parents[1]


def test_supported_python_range_and_fast_matrix_are_aligned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert project["project"]["requires-python"] == ">=3.13"
    assert 'python-version: ["3.13", "3.14"]' in workflow
    assert 'python-version: ["3.10"' not in workflow
    assert "cancel-in-progress: true" in workflow
    assert "matrix.python-version == '3.14'" in workflow
    assert "uv build --quiet" in workflow


def test_full_cli_workflow_is_opt_in_and_covers_both_families() -> None:
    workflow = (ROOT / ".github/workflows/full-cli.yml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)
    assert "jobs" in parsed

    assert "workflow_dispatch:" in workflow
    assert "types: [labeled, synchronize, reopened]" in workflow
    assert "ci:full" in workflow
    assert "contains(github.event.pull_request.labels.*.name, 'ci:full')" in workflow
    assert "cancel-in-progress: true" in workflow
    assert 'python-version: "3.14"' in workflow
    assert workflow.count("--num-images 10") == 2
    assert workflow.count("--workers 2") >= 2
    assert workflow.count("--qa-samples 3") == 2
    assert "landing-ci.yaml" in workflow
    assert "manometro-ci.yaml" in workflow
    assert workflow.count("run status") == 2
    assert workflow.count("verify_ci_pool.py") == 2
    assert workflow.count(" export ") == 2
    assert "retention-days: 7" in workflow
    assert "outputs/ci/**/images/**" not in workflow


def test_windows_validation_uses_latest_supported_python() -> None:
    workflow = (ROOT / ".github/workflows/windows-full.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.14"' in workflow


def test_pr_template_records_full_cli_decision() -> None:
    template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
    assert "ci:full" in template
    assert "Full CLI validation" in template
