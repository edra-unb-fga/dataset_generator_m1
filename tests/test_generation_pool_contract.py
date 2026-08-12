import json
import threading
from pathlib import Path

import numpy as np

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import GenerationOptions, generate_pool
from dataset_generator_m1.run_control import request_run_action
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
    assert (pool / "masks").is_dir()
    assert (pool / "qa" / "index.html").exists()
    manifest = json.loads((pool / "run.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["capabilities"] == {
        "detection_boxes": True,
        "full_instance_coverage": True,
        "visible_instance_coverage": True,
    }
    assert manifest["annotation_policy"] == {"alpha_threshold": 8, "default_mask_semantics": "visible"}
    assert manifest["preflight"]["status"] == "valid"
    assert manifest["preflight"]["receipt_binding"]["value"]["workers"] == 1
    samples = [json.loads(line) for line in (pool / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(samples) == 1
    assert samples[0]["sample_id"].startswith("pool-test_000000_")
    assert samples[0]["stage_timings_ns"]["scene_render"] > 0
    assert samples[0]["stage_timings_ns"]["image_encode_write"] > 0
    assert samples[0]["attempted_instances"] >= len(samples[0]["annotations"])
    assert samples[0]["annotations"][0]["source_group"]
    assert samples[0]["schema_version"] == 2
    assert samples[0]["annotations"][0]["instance_id"].startswith("instance-")
    evidence = samples[0]["mask_evidence"]
    assert evidence["path"].startswith("masks/")
    assert evidence["byte_count"] == (pool / evidence["path"]).stat().st_size
    assert samples[0]["stage_timings_ns"]["mask_encode"] > 0
    assert samples[0]["stage_timings_ns"]["mask_write"] > 0
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


def test_pool_v1_cannot_resume_as_v2(tmp_path: Path) -> None:
    resolved = small_resolved()
    pool = tmp_path / "legacy"
    pool.mkdir()
    (pool / "run.json").write_text(
        json.dumps({"schema_version": 1, "contract_hash": resolved.contract_hash}), encoding="utf-8"
    )

    try:
        generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=1, resume=True))
    except ValueError as exc:
        assert "pool schema v1" in str(exc).lower()
    else:
        raise AssertionError("Pool-v1 resume must require a new pool-v2 run")


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


def test_external_stop_creates_a_resumable_pool(tmp_path: Path, monkeypatch) -> None:
    import dataset_generator_m1.generator as generator_module

    resolved = small_resolved()
    profile = resolved.profile.model_copy(
        update={"run": resolved.profile.run.model_copy(update={"num_images": 3})}
    )
    resolved = resolved.model_copy(update={"profile": profile})
    pool = tmp_path / "controlled"
    entered = threading.Event()
    release = threading.Event()

    def fake_slot(_resolved, _catalog, slot, starting_attempt, _pid):
        entered.set()
        release.wait(timeout=5)
        return {
            "accepted": True,
            "image": np.zeros((128, 192, 3), dtype=np.uint8),
            "mask_archive": b"",
            "rejections": [],
            "record": {
                "schema_version": 2,
                "slot": slot,
                "candidate_attempt": starting_attempt,
                "geometry_signature": f"slot-{slot}",
                "intentional_negative": True,
                "attempted_instances": 0,
                "annotations": [],
                "mask_evidence": {"schema_version": 1, "format": "npz-cropped-alpha-v1", "sha256": __import__("hashlib").sha256(b"").hexdigest(), "byte_count": 0, "image_size": [192, 128], "alpha_threshold": 8, "instances": []},
                "rejected_instances": [],
                "background": {"recipe_id": "direct", "node_timings_ns": {}, "qa": {}, "warnings": []},
                "stage_timings_ns": {"scene_render": 1},
                "execution": {"worker_pid": 1, "worker_process": False},
            },
        }

    monkeypatch.setattr(generator_module, "_produce_slot", fake_slot)
    result: dict = {}

    def run() -> None:
        result.update(generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=1)))

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(timeout=10)
    request_run_action(pool, "stop")
    release.set()
    thread.join(timeout=15)

    assert result["status"] == "interrupted"
    assert result["accepted_samples"] == 1
    resumed = generate_pool(resolved, pool, GenerationOptions(display="quiet", workers=1, resume=True))
    assert resumed["status"] == "complete"
    assert resumed["accepted_samples"] == 3
