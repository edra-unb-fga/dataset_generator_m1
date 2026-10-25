import json

import pytest

from dataset_generator_m1.inspection import inspect_pool


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_manifest_numbers_are_structured_findings(tmp_path, value):
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa/index.html").write_text("<html></html>")
    for name in ("run.json", "summary.json", "control.json"):
        (tmp_path / name).write_text(json.dumps({"schema_version": value}))
    for name in ("samples.jsonl", "rejections.jsonl", "metrics.jsonl", "control-events.jsonl"):
        (tmp_path / name).touch()
    result = inspect_pool(tmp_path)
    assert result["status"] == "invalid"
    assert result["findings"][0]["code"] == "INVALID_POOL_RECORD"
