import json
from pathlib import Path

import cv2
from PIL import Image
import pytest

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.decoded_cache import cache_scope, cache_stats, decode
from dataset_generator_m1.execution import execution_scope, plan_execution
from dataset_generator_m1.identities import generation_identity
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.models import ExecutionConfig
from dataset_generator_m1.performance import performance_fingerprint


def _resolved(**policy):
    r = load_profile("examples/configs/landing_minimal.yaml")
    return r.model_copy(update={"profile": r.profile.model_copy(update={"execution": ExecutionConfig(**policy)})})


def test_execution_budgets_are_explicit_without_quality_changes():
    r = _resolved(workers="auto", cpu_budget=4, native_threads=2, ram_budget_mb=4096, decoded_cache_mb=128)
    plan = plan_execution(r, available_ram=8 * 1024**3, logical_cpus=8)
    assert plan.workers == 2
    assert plan.cache_bytes_per_worker == 64 * 1024**2
    assert plan.max_in_flight == 4
    assert r.profile.output.image_size == (1280, 1280)
    with pytest.raises(ValueError, match="cpu_budget"):
        plan_execution(_resolved(workers=4, cpu_budget=2))
    with pytest.raises(ValueError, match="max_in_flight"):
        plan_execution(_resolved(workers=2, max_in_flight=1))
    with pytest.raises(ValueError, match="cache"):
        plan_execution(_resolved(ram_budget_mb=256, decoded_cache_mb=512))


def test_cache_is_bounded_and_never_returns_mutable_shared_pixels(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGBA", (16, 16), (10, 20, 30, 42)).save(path)
    with cache_scope(1024):
        a = decode(path, "RGBA")
        a[:] = 0
        b = decode(path, "RGBA")
        assert b[0, 0].tolist() == [10, 20, 30, 42]
        assert cache_stats()["hits"] == 1
        assert cache_stats()["retained_bytes"] <= 1024
    assert cache_stats()["retained_bytes"] == 0


def test_native_threads_restored_after_failure():
    before = cv2.getNumThreads()
    with pytest.raises(RuntimeError):
        with execution_scope(plan_execution(_resolved(native_threads=1))):
            assert cv2.getNumThreads() == 1
            raise RuntimeError("test")
    assert cv2.getNumThreads() == before


def test_probe_uses_configured_native_threads_and_restores_them(monkeypatch):
    from dataset_generator_m1.generator import probe_profile
    before = cv2.getNumThreads()
    calls = []
    def produce(*_args):
        calls.append(cv2.getNumThreads())
        return {"accepted": True, "record": {"annotations": []}, "rejections": []}
    monkeypatch.setattr("dataset_generator_m1.generator._produce_slot", produce)
    assert len(probe_profile(_resolved(native_threads=1), timeout_seconds=60)) == 3
    assert calls == [1, 1, 1, 1]
    assert cv2.getNumThreads() == before


def test_portable_content_identity_distinguishes_execution_and_provenance(tmp_path):
    r = _resolved()
    catalog = build_asset_catalog(r)
    initial = generation_identity(r, catalog)
    changed = _resolved(workers=2, native_threads=1, decoded_cache_mb=64)
    assert generation_identity(changed, catalog) == initial
    assert performance_fingerprint(changed) != performance_fingerprint(r)
    # Move source paths and recipe-file provenance, retaining logical/content identity.
    moved_assets = r.profile.assets.model_copy(update={"backgrounds": r.profile.assets.backgrounds.model_copy(update={"paths": ("/elsewhere",)})})
    relocated = r.model_copy(update={"profile": r.profile.model_copy(update={"assets": moved_assets})})
    assert generation_identity(relocated, catalog) == initial


def test_production_benchmark_uses_real_masks_and_preserves_content(tmp_path):
    from dataset_generator_m1.execution_benchmark import production_benchmark
    from dataset_generator_m1.models import OutputConfig, AppearanceConfig, SamplingConfig
    r = _resolved(native_threads=1)
    profile = r.profile.model_copy(update={"output": OutputConfig(image_size=(128, 128)),
        "appearance": AppearanceConfig(), "sampling": SamplingConfig(instances_per_image=(1,1), foreground_size=(.2,.2))})
    r = r.model_copy(update={"profile": profile})
    matrix = tmp_path / "matrix.yaml"
    matrix.write_text("schema_version: 1\nvariants:\n  baseline: {}\n  cache: {decoded_cache_mb: 8}\n")
    result = production_benchmark(r, tmp_path / "bench", matrix_file=matrix, samples=1, repeats=1, warmup=0)
    assert result["status"] == "complete"
    assert len({row["content_signature"] for row in result["records"]}) == 1
    assert all("mask_encode" in row["stage_work"] for row in result["records"])
    assert result["low_sample"]


def test_cost_revision_changes_execution_and_observation_identity_only(monkeypatch):
    from dataset_generator_m1 import performance_version
    from dataset_generator_m1.identities import execution_identity
    resolved=_resolved(native_threads=1)
    catalog=build_asset_catalog(resolved)
    plan=plan_execution(resolved)
    generation=generation_identity(resolved,catalog)
    fingerprint=performance_fingerprint(resolved)
    execution=execution_identity(plan)
    monkeypatch.setattr(performance_version,'IMPLEMENTATION','different-cost-implementation')
    assert generation_identity(resolved,catalog)==generation
    assert performance_fingerprint(resolved)!=fingerprint
    assert execution_identity(plan)['sha256']!=execution['sha256']
