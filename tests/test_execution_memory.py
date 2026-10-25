from pathlib import Path

from PIL import Image
import pytest

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.models import ExecutionConfig


def resolved(**policy):
    value=load_profile('examples/configs/landing-pad_minimal.yaml')
    return value.model_copy(update={'profile':value.profile.model_copy(update={'execution':ExecutionConfig(**policy)})})


@pytest.mark.parametrize('budget',[256,1800,4096,8192,16384])
def test_auto_accounts_for_complete_plan_before_selecting_workers(budget):
    value=resolved(workers='auto',native_threads=1,ram_budget_mb=budget)
    plan=plan_execution(value,
                        available_ram=8*1024**3,logical_cpus=24)
    minimum=plan_execution(value,1,available_ram=8*1024**3,logical_cpus=24)
    if minimum.estimated_peak_bytes<=plan.ram_budget_bytes:
        assert plan.estimated_peak_bytes<=plan.ram_budget_bytes
    else:
        assert plan.workers==1
        assert any('RAM_ESTIMATE_EXCEEDS_BUDGET' in warning for warning in plan.warnings)


def test_auto_respects_explicit_queue_capacity():
    plan=plan_execution(resolved(workers='auto',native_threads=1,max_in_flight=2,ram_budget_mb=16384),
                        available_ram=32*1024**3,logical_cpus=24)
    assert plan.workers<=2
    assert plan.max_in_flight==2


def test_memory_accounts_for_source_dimensions_and_cover_expansion(tmp_path,monkeypatch):
    square=tmp_path/'square.png';wide=tmp_path/'wide.png'
    Image.new('RGB',(100,100)).save(square);Image.new('RGB',(4000,10)).save(wide)
    value=resolved(native_threads=1)
    def with_background(path:Path):
        assets=value.profile.assets.model_copy(update={'backgrounds':value.profile.assets.backgrounds.model_copy(update={'paths':(str(path),)})})
        return value.model_copy(update={'profile':value.profile.model_copy(update={'assets':assets})})
    def refuse_decode(*args,**kwargs):raise AssertionError('Planning must inspect headers without decoding pixels')
    monkeypatch.setattr(Image.Image,'load',refuse_decode)
    small=plan_execution(with_background(square));large=plan_execution(with_background(wide))
    assert large.estimated_peak_bytes>small.estimated_peak_bytes


def test_memory_increases_with_native_thread_reserve():
    one=plan_execution(resolved(workers=6,native_threads=1,max_in_flight=6))
    many=plan_execution(resolved(workers=6,native_threads=24,max_in_flight=6))
    assert many.estimated_peak_bytes>one.estimated_peak_bytes
    assert any('OVERSUBSCRIBED' in warning for warning in many.warnings)


def test_minimum_unfittable_plan_is_explicit():
    plan=plan_execution(resolved(workers='auto',native_threads=1,ram_budget_mb=256),
                        available_ram=1024**3,logical_cpus=24)
    assert plan.workers==1
    assert any('RAM_ESTIMATE_EXCEEDS_BUDGET' in warning for warning in plan.warnings)


def test_source_header_cache_invalidates_on_file_change(tmp_path):
    from dataset_generator_m1.memory_planning import source_shapes
    path=tmp_path/'source.png';Image.new('RGB',(10,10)).save(path)
    value=resolved(native_threads=1)
    assets=value.profile.assets.model_copy(update={'foregrounds':value.profile.assets.foregrounds.model_copy(update={'paths':(str(path),)})})
    value=value.model_copy(update={'profile':value.profile.model_copy(update={'assets':assets})})
    assert source_shapes(value)['foreground_pixels']==100
    Image.new('RGB',(30,40)).save(path)
    assert source_shapes(value)['foreground_pixels']==1200


def test_missing_source_dimensions_are_explicit(tmp_path):
    value=resolved(native_threads=1)
    assets=value.profile.assets.model_copy(update={'foregrounds':value.profile.assets.foregrounds.model_copy(update={'paths':(str(tmp_path/'missing.png'),)})})
    value=value.model_copy(update={'profile':value.profile.model_copy(update={'assets':assets})})
    plan=plan_execution(value)
    assert not plan.memory_estimate['source_dimensions_complete']
    assert any('SOURCE_DIMENSIONS_INCOMPLETE' in warning for warning in plan.warnings)
