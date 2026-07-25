import json
from pathlib import Path

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import GenerationOptions, generate_pool
from dataset_generator_m1.models import OutputConfig, ReportConfig, RunConfig, SamplingConfig


def small_resolved():
    resolved = load_profile("examples/configs/landing_minimal.yaml")
    profile = resolved.profile.model_copy(
        update={
            "output": OutputConfig(image_size=(192, 128), image_format="png"),
            "run": RunConfig(label="pool-test", num_images=1, seed=31, max_candidate_attempts=5),
            "sampling": SamplingConfig(
                instances_per_image=(1, 1),
                foreground_size=(0.16, 0.16),
                bbox_spacing=0.01,
                placement_attempts=20,
                min_visible_bbox_fraction=0.70,
            ),
            "report": ReportConfig(qa_samples=1),
        }
    )
    return resolved.model_copy(update={"profile": profile})


def test_generation_pool_is_auditable_and_resumable(tmp_path: Path) -> None:
    resolved = small_resolved()
    pool = tmp_path / "pool"

    first = generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=1))

    assert first["status"] == "complete"
    assert first["accepted_samples"] == 1
    assert (pool / "run.json").exists()
    assert (pool / "samples.jsonl").exists()
    assert (pool / "rejections.jsonl").exists()
    assert (pool / "metrics.jsonl").exists()
    assert (pool / "summary.json").exists()
    assert (pool / "qa" / "index.html").exists()
    samples = [json.loads(line) for line in (pool / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(samples) == 1
    assert samples[0]["sample_id"].startswith("pool-test_000000_")
    assert samples[0]["stage_timings_ns"]["scene_render"] > 0
    assert samples[0]["stage_timings_ns"]["image_encode_write"] > 0
    assert samples[0]["attempted_instances"] >= len(samples[0]["annotations"])
    assert samples[0]["annotations"][0]["source_group"]
    assert Path(samples[0]["image_path"]).name.endswith(".png")
    image_path = pool / samples[0]["image_path"]
    committed_mtime = image_path.stat().st_mtime_ns

    # Simulate a crash after the atomic sample commit but before the aggregate
    # JSONL append became durable. Resume must reconcile the audit stream.
    (pool / "samples.jsonl").write_text("", encoding="utf-8")
    resumed = generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=1, resume=True))

    assert resumed["status"] == "complete"
    assert len((pool / "samples.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert image_path.stat().st_mtime_ns == committed_mtime


def test_process_workers_preserve_geometry_and_annotations(tmp_path: Path) -> None:
    resolved = small_resolved()
    serial_pool = tmp_path / "serial"
    process_pool = tmp_path / "process"

    serial = generate_pool(resolved, serial_pool, GenerationOptions(display="quiet", workers=1))
    parallel = generate_pool(resolved, process_pool, GenerationOptions(display="quiet", workers=2))

    serial_sample = json.loads((serial_pool / "samples.jsonl").read_text(encoding="utf-8"))
    process_sample = json.loads((process_pool / "samples.jsonl").read_text(encoding="utf-8"))
    assert serial["worker_count"] == 1
    assert parallel["worker_count"] == 2
    assert process_sample["execution"]["worker_process"] is True
    assert process_sample["geometry_signature"] == serial_sample["geometry_signature"]
    assert process_sample["scene_to_output"] == serial_sample["scene_to_output"]
    assert process_sample["annotations"] == serial_sample["annotations"]
