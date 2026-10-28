import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('prepare_blenderproc_run',Path('scripts/prepare_blenderproc_run.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_prepare_freezes_adaptive_guards_and_saved_l4_profile(tmp_path,monkeypatch):
    monkeypatch.setattr(module.shutil,'which',lambda name:None)
    observed={}
    def fake_prepare(config,output):
        observed.update(json.loads(Path(config).read_text()));Path(output).mkdir();return {'identity':'test-identity'}
    monkeypatch.setattr(module,'prepare',fake_prepare)
    config=Path('experiments/blenderproc/pilot-fast.example.json')
    value=module.prepare_run(config,tmp_path/'run',screen_profile='colab-l4-camera-study',gpu_guard='off')
    assert value['status']=='complete' and value['screen_profile']=='colab-l4-camera-study'
    assert (observed['workers'],observed['threads'],observed['execution_profile'])==(6,2,'gpu-guarded')
    assert Path(observed['execution_policy']).is_file() and Path(value['guard_basis']).is_file()
    assert json.loads((tmp_path/'run'/'setup-status.json').read_text())['guards']==value['guards']
    with pytest.raises(FileExistsError):module.prepare_run(config,tmp_path/'run',gpu_guard='off')


def test_explicit_gpu_profile_does_not_silently_skip_missing_telemetry(tmp_path,monkeypatch):
    monkeypatch.setattr(module.shutil,'which',lambda name:None)
    with pytest.raises(ValueError,match='GPU profile requires'):
        module.prepare_run('experiments/blenderproc/pilot-fast.example.json',tmp_path/'run',screen_profile='colab-l4-camera-study')
    assert not (tmp_path/'run').exists()


def test_l4_profile_scales_with_resolution():
    data=json.loads(Path('experiments/blenderproc/execution/quick-screen-profiles.json').read_text())
    rules=data['profiles']['colab-l4-camera-study']['rules']
    assert (rules[0]['workers'],rules[0]['threads'],rules[0]['max_pixels'])==(6,2,640*640)
    assert (rules[1]['workers'],rules[1]['threads'],rules[1]['max_pixels'])==(4,1,None)


def test_cpu_profile_does_not_query_gpu_just_because_tool_exists(tmp_path,monkeypatch):
    monkeypatch.setattr(module.shutil,'which',lambda name:'/fake/nvidia-smi')
    monkeypatch.setattr(module,'prepare',lambda config,output: {'identity':'cpu-identity'})
    result=module.prepare_run('experiments/blenderproc/pilot-fast.example.json',tmp_path/'cpu',screen_profile='local-cpu')
    assert not result['gpu_guard_measured'] and not result['gpu_guard_active']


def test_guard_setup_failure_records_error_without_preparing(tmp_path,monkeypatch):
    import subprocess
    monkeypatch.setattr(module.shutil,'which',lambda name:'/fake/nvidia-smi')
    def fail(*args,**kwargs):raise subprocess.CalledProcessError(1,'fake',stderr='exactly one NVIDIA GPU required')
    monkeypatch.setattr(module.subprocess,'run',fail)
    monkeypatch.setattr(module,'prepare',lambda *args:pytest.fail('must not prepare after guard failure'))
    with pytest.raises(RuntimeError,match='exactly one NVIDIA GPU'):
        module.prepare_run('experiments/blenderproc/pilot-fast.example.json',tmp_path/'bad',screen_profile='colab-l4-camera-study')
    assert json.loads((tmp_path/'bad'/'setup-status.json').read_text())['status']=='failed'


def test_explicit_gpu_guard_off_clears_inherited_limit(tmp_path,monkeypatch):
    source=json.loads(Path('experiments/blenderproc/execution/profiles.json').read_text())
    source['guards']['min_gpu_free_mib']=1234
    policy=tmp_path/'source-policy.json';policy.write_text(json.dumps(source))
    config=json.loads(Path('experiments/blenderproc/pilot-fast.example.json').read_text())
    config['execution_policy']=str(policy)
    config_path=tmp_path/'config.json';config_path.write_text(json.dumps(config))
    monkeypatch.setattr(module,'prepare',lambda config,output: {'identity':'test-identity'})
    result=module.prepare_run(config_path,tmp_path/'run',gpu_guard='off')
    basis=json.loads(Path(result['guard_basis']).read_text())
    saved=json.loads(Path(result['execution_policy']).read_text())
    assert not result['gpu_guard_active'] and not result['gpu_guard_measured']
    assert saved['guards']['min_gpu_free_mib'] is None
    assert basis['gpu_guard_disabled_explicitly'] is True
    assert json.loads(policy.read_text())['guards']['min_gpu_free_mib']==1234
