import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from helpers import write_derived_composer


spec = importlib.util.spec_from_file_location('surface_2d_study', Path(__file__).resolve().parents[1]/'scripts/study_surface_2d.py')
study = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = study
spec.loader.exec_module(study)


def matrix_value():
    return {'schema_version': 1, 'samples': 2, 'warmups': 1, 'repetitions': 1,
        'resolutions': [[96, 96]], 'prepare_evaluation': True,
        'shared_scene': {'lighting': {'probability': 1, 'gain': [1, 1], 'gradient': [0, 0], 'tint': 0}},
        'variants': [{'name': 'pristine', 'wear': {'fade': 0, 'dirt': 0, 'scratches': 0, 'marks': 0}},
                     {'name': 'shade', 'wear': {}, 'shade': {'probability': 1, 'strength': [.6, .6], 'radius_fraction': [.7, .7]}}]}


def test_paired_study_produces_inspected_pools_and_exact_coco(tmp_path):
    config = write_derived_composer(tmp_path, 'landing-pad', {'background_mixing': {'recipe_weights': {'direct': 1}}, 'reporting': {'qa_samples': 0}})
    composer = yaml.safe_load(config.read_text())
    composer['appearance'] = {'preset': 'builtin:appearance/no-appearance'}
    config.write_text(yaml.safe_dump(composer, sort_keys=False))
    matrix = tmp_path/'matrix.json';matrix.write_text(json.dumps(matrix_value()))
    execution = tmp_path/'execution.json';execution.write_text(json.dumps({'workers': 1, 'native_threads': 1}))
    root = tmp_path/'study'
    result = study.run_study(config, matrix, root, execution)
    assert result['status'] == 'complete' and result['all_content_signatures_equal']
    rows = result['records']
    assert [r['variant'] for r in rows] == ['pristine', 'shade']
    assert rows[0]['content_signature'] == rows[1]['content_signature']
    assert all(r['accepted'] == 2 and r['warmup']['accepted'] == 1 for r in rows)
    assert all(r['inspection'] == 'valid' and r['images_per_second'] > 0 for r in rows)
    assert all(r['evaluation']['images'] == 2 and r['evaluation']['annotations'] > 0 for r in rows)
    assert all(r['execution']['workers'] == 1 and r['execution']['native_threads'] == 1 for r in rows)
    assert all(r['unique_measured_scene_intents'] == 2 for r in rows)
    assert all(r['wear_effect_traces'][0][0]['type'] == 'SurfaceWear' for r in rows)
    assert any(effect['lighting']['shade']['applied'] for effect in rows[1]['scene_effects'])
    assert all(r['low_sample'] for r in result['medians'])
    assert json.loads((root/'progress.json').read_text())['status'] == 'complete'
    assert (root/'driver-source.py').is_file()
    with pytest.raises(ValueError, match='fresh'):
        study.run_study(config, matrix, root, execution)


@pytest.mark.parametrize('change', [{'resolutions': []}, {'resolutions': [[640, 640], [640, 640]]},
    {'resolutions': [[640, 0]]}, {'variants': []}, {'samples': 0},
    {'variants': [{'name': '../escape', 'wear': {}}]},
    {'shared_scene': {'lighting': {'shade': {'probability': .5}}}}])
def test_matrix_rejects_invalid_or_ambiguous_study_shapes(change):
    with pytest.raises(ValueError):
        study.Matrix.model_validate({**matrix_value(), **change})
