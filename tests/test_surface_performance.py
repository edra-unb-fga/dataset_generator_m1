import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('study_surface_performance', Path(__file__).resolve().parents[1] / 'scripts/study_surface_performance.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(tmp_path, name, mask, status='accepted'):
    path = tmp_path/name
    path.mkdir()
    np.savez_compressed(path/'masks.npz', visible=mask, full=mask)
    job = {'scene_index': 2, 'reference_scene_index': 2, 'seed': 5, 'scene': {'objects': [1]}, 'ground_index': 0}
    result = {'status': status, 'attempts': [{'attempt': 0, 'support': [1], 'rejection': None, 'setup_seconds': 123}]}
    return (job, path, result)


def test_evidence_detects_pixel_and_acceptance_changes(tmp_path):
    mask = np.array([[[0, 1], [1, 0]]], dtype=np.uint8)
    a = row(tmp_path, 'a', mask)
    b = row(tmp_path, 'b', mask.copy())
    c = row(tmp_path, 'c', 1-mask)
    d = row(tmp_path, 'd', mask, 'rejected')
    assert module.evidence([a]) == module.evidence([b])
    assert module.evidence([a]) != module.evidence([c])
    assert module.evidence([a]) != module.evidence([d])


def test_checked_phase_refuses_failed_run(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'run_study', lambda *args, **kwargs: {'status': 'failed'})
    (tmp_path/'runs.json').write_text('[]')
    with pytest.raises(RuntimeError, match='Incomplete command'):
        module.checked_phase(tmp_path, {}, ['001-core-fast'], 'blenderproc', 'blender')


def test_benchmark_accepts_saved_design_and_smaller_configuration():
    small = {'warmups': 1, 'measured': 3, 'repetitions': 1, 'resolutions': [[256, 256]]}
    assert module.validate_benchmark(small) == small
    warm, measured = module.phase_ids(small, 'wear')
    assert warm == ['000-wear-fast']
    assert measured == ['001-wear-fast', '002-wear-fast', '003-wear-fast']
    matrix = __import__('json').loads((Path(__file__).resolve().parents[1] / 'experiments/blenderproc/studies/surface-integration.json').read_text())
    assert module.validate_benchmark(matrix['benchmark']) == matrix['benchmark']


@pytest.mark.parametrize('change', [
    {'warmups': True}, {'measured': 0}, {'repetitions': 0},
    {'resolutions': [[256, 256], [256, 256]]}, {'resolutions': [[1, 256]]},
    {'warmups': 5, 'measured': 96},
])
def test_benchmark_rejects_invalid_inputs(change):
    benchmark = {'warmups': 1, 'measured': 3, 'repetitions': 1, 'resolutions': [[256, 256]]}
    benchmark.update(change)
    with pytest.raises(ValueError):
        module.validate_benchmark(benchmark)
