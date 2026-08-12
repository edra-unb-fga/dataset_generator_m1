from __future__ import annotations

import json
from pathlib import Path

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import GenerationOptions, generate_pool
from dataset_generator_m1.inspection import inspect_pool
from dataset_generator_m1.performance import append_production_observation, performance_fingerprint
from dataset_generator_m1.preparation import PreparationRequest, prepare_generation


def _resolved(*, count: int = 1, seed: int = 31):
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    run = resolved.profile.run.model_copy(update={"num_images": count, "seed": seed, "max_candidate_attempts": 5})
    return resolved.model_copy(update={"profile": resolved.profile.model_copy(update={"run": run})})


def test_prepared_generation_binds_contract_output_workers_and_environment(tmp_path: Path) -> None:
    prepared = prepare_generation(PreparationRequest(_resolved(), tmp_path / "pool", workers=1))

    assert prepared.preflight["status"] == "valid"
    assert prepared.workers == 1
    prepared.require_compatible(prepared.resolved, tmp_path / "pool", 1)
    try:
        prepared.require_compatible(prepared.resolved, tmp_path / "other", 1)
    except ValueError as exc:
        assert "invalidated" in str(exc)
    else:
        raise AssertionError("changing the destination must invalidate preparation")


def test_performance_fingerprint_ignores_count_and_seed() -> None:
    assert performance_fingerprint(_resolved(count=1, seed=3)) == performance_fingerprint(_resolved(count=20, seed=99))


def test_production_observations_are_sanitized_and_calibrate_after_three_runs(tmp_path: Path) -> None:
    path = tmp_path / "observations.jsonl"
    resolved = _resolved(count=10)
    summary = {
        "status": "complete",
        "elapsed_seconds": 20.0,
        "paused_seconds": 4.0,
        "candidate_attempts": 12,
        "accepted_samples": 10,
        "throughput_images_per_second": 0.5,
        "stage_timings": {"scene_render": {"count": 10, "total_ns": 1_000_000}},
    }
    for _ in range(3):
        append_production_observation(path, resolved, workers=2, summary=summary)

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    serialized = json.dumps(records)
    assert "username" not in serialized and "hostname" not in serialized
    prepared = prepare_generation(PreparationRequest(resolved, tmp_path / "pool", workers=2, observation_path=path))
    assert prepared.preflight["runtime"]["confidence"] == "local-production"
    assert prepared.preflight["runtime"]["observation_count"] == 3

    cross_worker = prepare_generation(PreparationRequest(resolved, tmp_path / "other", workers=1, observation_path=path))
    assert cross_worker.preflight["runtime"]["confidence"] == "local-production-cross-worker"
    assert any(item["code"] == "LOCAL_OBSERVATION_CROSS_WORKER" for item in cross_worker.preflight["warnings"])


def test_inspection_reuses_generated_pool_contract_and_reports_corruption(tmp_path: Path) -> None:
    resolved = _resolved()
    prepared = prepare_generation(PreparationRequest(resolved, tmp_path / "pool", workers=1))
    result = generate_pool(
        resolved,
        tmp_path / "pool",
        GenerationOptions(display="quiet", workers=1, prepared=prepared),
    )
    assert result["status"] == "complete"
    valid = inspect_pool(tmp_path / "pool")
    assert valid["status"] == "valid"
    assert valid["samples"] == 1
    assert valid["mask_archives"] == 1

    image = next((tmp_path / "pool" / "images").iterdir())
    original_image = image.read_bytes()
    image.write_bytes(b"not an image")
    invalid = inspect_pool(tmp_path / "pool")
    assert invalid["status"] == "invalid"
    assert any(finding["code"] == "IMAGE_DECODE_FAILED" for finding in invalid["findings"])

    image.write_bytes(original_image)
    samples_path = tmp_path / "pool" / "samples.jsonl"
    original_samples = samples_path.read_text(encoding="utf-8")
    sample = json.loads(original_samples)
    sample["annotations"][0]["bbox"] = [-1, 0, 5, 5]
    samples_path.write_text(json.dumps(sample) + "\n", encoding="utf-8")
    assert any(item["code"] == "ANNOTATION_OUT_OF_BOUNDS" for item in inspect_pool(tmp_path / "pool")["findings"])

    samples_path.write_text(original_samples, encoding="utf-8")
    qa_path = tmp_path / "pool" / "qa" / "index.html"
    original_qa = qa_path.read_text(encoding="utf-8")
    qa_path.write_text(original_qa.replace("</main>", '<img src="missing.jpg"></main>'), encoding="utf-8")
    assert any(item["code"] == "BROKEN_QA_LINK" for item in inspect_pool(tmp_path / "pool")["findings"])

    qa_path.write_text(original_qa, encoding="utf-8")
    summary_path = tmp_path / "pool" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["accepted_samples"] = 99
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    assert any(item["code"] == "SAMPLE_COUNT_DRIFT" for item in inspect_pool(tmp_path / "pool")["findings"])


def test_inspection_rejects_mask_corruption_and_bbox_drift(tmp_path: Path) -> None:
    resolved = _resolved()
    pool = tmp_path / "pool"
    generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=1))
    sample = json.loads((pool / "samples.jsonl").read_text(encoding="utf-8"))
    mask_path = pool / sample["mask_evidence"]["path"]
    original = mask_path.read_bytes()
    mask_path.write_bytes(original[:-3] + b"bad")
    findings = inspect_pool(pool)["findings"]
    assert any(item["code"] == "MASK_EVIDENCE_INVALID" for item in findings)

    mask_path.write_bytes(original)
    record_path = pool / "state" / "samples" / "00000000.json"
    state = json.loads(record_path.read_text(encoding="utf-8"))
    state["annotations"][0]["bbox"] = [0, 0, 1, 1]
    record_path.write_text(json.dumps(state), encoding="utf-8")
    # Rebuild readable JSONL from the modified state to simulate internally
    # consistent record corruption rather than journal drift.
    (pool / "samples.jsonl").write_text(json.dumps(state) + "\n", encoding="utf-8")
    findings = inspect_pool(pool)["findings"]
    assert any(item["code"] == "MASK_BBOX_MISMATCH" for item in findings)


def test_pool_v1_remains_inspectable_without_mask_capability(tmp_path: Path) -> None:
    pool = tmp_path / "legacy"
    (pool / "images").mkdir(parents=True)
    (pool / "qa").mkdir()
    from PIL import Image

    Image.new("RGB", (8, 8), "white").save(pool / "images" / "sample.png")
    manifest = {
        "schema_version": 1,
        "contract_hash": "legacy",
        "profile": {"run": {"num_images": 1}, "output": {"image_size": [8, 8]}},
    }
    sample = {"sample_id": "legacy", "image_path": "images/sample.png", "annotations": []}
    summary = {"status": "complete", "accepted_samples": 1, "contract_hash": "legacy"}
    control = {"actual_state": "complete"}
    for name, value in (("run.json", manifest), ("summary.json", summary), ("control.json", control)):
        (pool / name).write_text(json.dumps(value), encoding="utf-8")
    (pool / "samples.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    for name in ("rejections.jsonl", "metrics.jsonl", "control-events.jsonl"):
        (pool / name).write_text("", encoding="utf-8")
    (pool / "qa" / "index.html").write_text("<html></html>", encoding="utf-8")

    result = inspect_pool(pool)
    assert result["status"] == "valid"
    assert result["pool_schema_version"] == 1
    assert result["mask_archives"] == 0


def test_malformed_observation_cache_is_visible_but_not_fatal(tmp_path: Path) -> None:
    cache = tmp_path / "observations.jsonl"
    cache.write_text("not json\n", encoding="utf-8")
    prepared = prepare_generation(PreparationRequest(_resolved(), tmp_path / "pool", workers=1, observation_path=cache))
    assert prepared.preflight["status"] == "valid"
    assert any(item["code"] == "IGNORED_MALFORMED_OBSERVATION" for item in prepared.preflight["warnings"])
