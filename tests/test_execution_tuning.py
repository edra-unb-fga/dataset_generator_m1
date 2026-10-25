from copy import deepcopy
import json

import pytest

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.execution_tuning import execution_candidates, recommend_execution, save_tuning_result, tuning_context
from dataset_generator_m1.models import ExecutionConfig

GIB = 2**30
HARDWARE = {'logical_cpus': 16, 'usable_cpus': 8, 'total_memory_bytes': 16*GIB,
            'available_memory_bytes': 10*GIB, 'system': 'test-os', 'machine': 'test-arch'}


@pytest.fixture
def resolved():
    return load_profile('examples/configs/landing-pad_minimal.yaml')


def study_for(resolved, rates=((1., 1.01, .99), (1.03, 1.04, 1.02))):
    context = tuning_context(resolved, hardware=HARDWARE)
    records = []
    for count, values in zip((3, 4), rates):
        policy = ExecutionConfig(workers=count, native_threads=1, max_in_flight=count)
        current = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'execution': policy})})
        execution = plan_execution(current, available_ram=10*GIB, logical_cpus=8).as_dict()
        for repeat, rate in enumerate(values):
            records.append({'variant': f'w{count}', 'repeat': repeat, 'status': 'complete', 'inspection': 'valid',
                'accepted': 48, 'attempts': 49, 'active_seconds': 48/rate, 'throughput': rate,
                'execution': execution, 'source': {'commit': 'abc', 'dirty': False},
                'software': context['software'], 'tuning_context': context,
                'content_signature': 'a'*64, 'pixel_signature': 'b'*64, 'generation_identity': {'sha256': 'c'*64},
                'guard_limits': {'min_available_gib': 2, 'max_swap_out_mib': 16, 'cell_timeout_seconds': 240, 'rss_limit_gib': 8},
                'initial_available_memory_bytes': 9*GIB, 'minimum_available_memory_bytes': 6*GIB,
                'swap_out_delta_bytes': 0, 'command_resource_observed': {'peak_rss_bytes': 3*GIB}})
    return {'kind': 'execution-control-study', 'status': 'complete', 'samples': 48, 'repeats': 3,
            'tuning_context': context, 'exact_encoded_images_equal': True,
            'geometry_annotation_masks_equal': True, 'records': records}


def test_candidates_fit_capacity_by_default_and_label_explicit_exploration(resolved):
    bounded = execution_candidates(resolved, hardware=HARDWARE, ram_budget_mb=2048)
    assert all(item['estimated_peak_bytes'] <= 2048*2**20 for item in bounded['forecasts'].values())
    assert bounded['starting_overrides']['execution']['native_threads'] == 1
    assert bounded['starting_overrides']['execution']['cpu_budget'] == 7
    explicit = execution_candidates(resolved, hardware=HARDWARE, workers=[3, 4], threads=[1], ram_budget_mb=2048)
    assert len(explicit['matrix']['variants']) == 2
    assert all(item['warnings'] for item in explicit['forecasts'].values())
    assert 'host' not in json.dumps(bounded['tuning_context'])


@pytest.mark.parametrize('changes', [{'cpu_budget': 0}, {'cpu_budget': 9}, {'ram_budget_mb': 0}, {'threads': [0]}, {'workers': [True]}])
def test_invalid_candidate_limits_are_rejected(resolved, changes):
    with pytest.raises(ValueError):
        execution_candidates(resolved, hardware=HARDWARE, **changes)


def test_near_best_choice_prefers_fewer_workers_and_preserves_content_contract(resolved):
    result = recommend_execution(resolved, study_for(resolved), hardware=HARDWARE)
    assert result['fastest']['workers'] == 4
    assert result['selected']['workers'] == 3
    assert result['overrides']['execution'] == {'workers': 3, 'native_threads': 1, 'max_in_flight': 3, 'decoded_cache_mb': 0}
    assert resolved.profile.execution.workers == 1
    fastest = recommend_execution(resolved, study_for(resolved), hardware=HARDWARE, tolerance_percent=0)
    assert fastest['selected']['workers'] == 4


def test_headroom_is_checked_against_current_availability(resolved):
    study = study_for(resolved)
    # Required headroom is 3 GiB observed drop ×1.1 + 2 GiB reserve.
    with pytest.raises(ValueError, match='current headroom'):
        recommend_execution(resolved, study, hardware={**HARDWARE, 'available_memory_bytes': 5*GIB})


@pytest.mark.parametrize('corrupt', ['aborted', 'short', 'duplicate', 'pixels', 'software', 'context', 'guard', 'counter', 'dirty', 'nan', 'unbounded'])
def test_recommendation_rejects_inadequate_or_incompatible_evidence(resolved, corrupt):
    study = deepcopy(study_for(resolved)); row = study['records'][0]
    if corrupt == 'aborted': study['status'] = 'guard-aborted'
    elif corrupt == 'short': study['samples'] = 12
    elif corrupt == 'duplicate': study['records'][1]['repeat'] = 0
    elif corrupt == 'pixels': row['pixel_signature'] = 'd'*64
    elif corrupt == 'software': row['software'] = {}
    elif corrupt == 'context': study['tuning_context'] = {}
    elif corrupt == 'guard': row['minimum_available_memory_bytes'] = GIB
    elif corrupt == 'counter': row['throughput'] = 4
    elif corrupt == 'dirty': row['source']['dirty'] = True
    elif corrupt == 'nan': row['throughput'] = float('nan')
    elif corrupt == 'unbounded': row['execution']['native_threads'] = None
    with pytest.raises(ValueError):
        recommend_execution(resolved, study, hardware=HARDWARE)


def test_context_ignores_count_seed_but_keeps_workload_and_qa(resolved):
    def update(subject, values):
        return resolved.model_copy(update={'profile': resolved.profile.model_copy(update={subject:getattr(resolved.profile, subject).model_copy(update=values)})})
    assert tuning_context(update('run', {'num_images': 999, 'seed': 66}), hardware=HARDWARE) == tuning_context(resolved, hardware=HARDWARE)
    assert tuning_context(update('report', {'qa_samples': 0}), hardware=HARDWARE) != tuning_context(resolved, hardware=HARDWARE)
    assert tuning_context(update('output', {'image_size': (64,64)}), hardware=HARDWARE) != tuning_context(resolved, hardware=HARDWARE)


def test_saved_recommendation_is_a_typed_override_and_never_overwrites(resolved, tmp_path):
    from dataset_generator_m1.overrides import build_override_plan
    result = recommend_execution(resolved, study_for(resolved), hardware=HARDWARE)
    save_tuning_result(result, tmp_path/'tuning')
    overrides = build_override_plan(override_file=tmp_path/'tuning/recommended-overrides.yaml')
    reloaded = load_profile('examples/configs/landing-pad_minimal.yaml', overrides.values)
    assert reloaded.profile.execution.workers == 3
    with pytest.raises(ValueError, match='must not exist'):
        save_tuning_result(result, tmp_path/'tuning')


def test_auto_uses_affinity_and_one_native_thread_even_after_resolution(resolved, monkeypatch):
    from types import SimpleNamespace
    from dataset_generator_m1 import execution
    from dataset_generator_m1.performance import performance_fingerprint
    monkeypatch.setattr(execution.os, 'cpu_count', lambda:32)
    monkeypatch.setattr(execution.psutil, 'Process', lambda:SimpleNamespace(cpu_affinity=lambda:[0,1,2,3]))
    profile = resolved.profile.model_copy(update={'execution': ExecutionConfig(workers='auto', ram_budget_mb=16384)})
    automatic = resolved.model_copy(update={'profile':profile})
    plan = plan_execution(automatic, available_ram=32*GIB)
    assert plan.workers == 3 and plan.native_threads == 1
    assert plan_execution(automatic, plan.workers).native_threads == 1
    explicit = automatic.model_copy(update={'profile':profile.model_copy(update={'execution':profile.execution.model_copy(update={'native_threads':1})})})
    assert performance_fingerprint(automatic) == performance_fingerprint(explicit)


def test_cli_recommendation_writes_one_json_result_and_reusable_overrides(resolved, tmp_path, monkeypatch, capsys):
    from dataset_generator_m1.cli import main
    from dataset_generator_m1 import execution_tuning
    monkeypatch.setattr(execution_tuning, 'hardware_snapshot', lambda:HARDWARE)
    source = tmp_path/'study.json'; source.write_text(json.dumps(study_for(resolved)))
    assert main(['execution','recommend','--config','examples/configs/landing-pad_minimal.yaml',
                 '--study',str(source),'--output-dir',str(tmp_path/'choice'),'--output-format','json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['selected']['workers'] == 3
    assert (tmp_path/'choice/recommended-overrides.yaml').is_file()


def test_auto_does_not_treat_an_oversized_cpu_budget_as_extra_hardware(resolved):
    profile = resolved.profile.model_copy(update={'execution':ExecutionConfig(workers='auto',cpu_budget=32,native_threads=2,ram_budget_mb=32768)})
    plan = plan_execution(resolved.model_copy(update={'profile':profile}), available_ram=64*GIB, logical_cpus=4)
    assert plan.workers == 2
    assert 'CPU_BUDGET_EXCEEDS_DETECTED_LOGICAL_CPUS' in plan.warnings
