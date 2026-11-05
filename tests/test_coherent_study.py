import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


path = Path('experiments/foreground-context/coherent-study/run.py').resolve()
spec = importlib.util.spec_from_file_location('coherent_study', path)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


@pytest.mark.parametrize('treatment', ['coherent-candidate', 'coherent-refined', 'coherent-directional'])
def test_profiles_keep_paired_run_and_use_requested_profiles(tmp_path, treatment):
    cells = study.profiles(tmp_path, 'landing', treatment, 4, 21, 640)
    baseline, candidate = cells['baseline'].profile, cells['candidate'].profile
    assert baseline.run == candidate.run
    assert baseline.output == candidate.output
    assert baseline.execution == candidate.execution
    assert candidate.scene.camera == baseline.scene.camera
    assert candidate.scene.perspective == baseline.scene.perspective
    assert baseline.scene.foreground_context is None
    assert candidate.scene.foreground_context is not None
    assert candidate.appearance.foreground[0].type == 'SurfaceWear'
    if treatment == 'coherent-directional':
        assert candidate.scene.lighting.directional_shade.probability == .75
        assert {effect.id for effect in candidate.appearance.final} == {'coherent-exposure', 'coherent-motion', 'coherent-compression'}


def test_runner_rejects_existing_output(tmp_path, monkeypatch):
    monkeypatch.setattr(study.psutil, 'virtual_memory', lambda: SimpleNamespace(total=16*2**30, available=8*2**30))
    with pytest.raises(FileExistsError):
        study.run(tmp_path, ['landing'], 'coherent-candidate', 1, 21, 640, study.DEFAULT_POLICY)
