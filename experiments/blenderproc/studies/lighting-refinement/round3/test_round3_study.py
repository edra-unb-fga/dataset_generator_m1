import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import importlib.util
spec = importlib.util.spec_from_file_location('lighting_round3_transform', HERE / 'transform.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
digest, transformed = module.digest, module.transformed


def test_coordinated_transforms_keep_source_and_controlled_ranges():
    lamps = [{'kind': 'AREA', 'location': [1., -1., 2.5], 'target': [0, 0, 0],
              'color': [1, 1, 1], 'power_w': 750., 'size_m': .85,
              'spot_size_rad': .9, 'spot_blend': .25}]
    original = json.dumps(lamps)
    broad = transformed(lamps, 'broad')[0]
    soft = transformed(lamps, 'soft')[0]
    assert json.dumps(lamps) == original
    assert broad['location'] == [1.5, -1.5, 3.25]
    assert broad['power_w'] == 650
    assert soft['power_w'] == 600
    assert broad['kind'] == soft['kind'] == 'AREA'
    assert transformed(lamps, 'baseline') == lamps


def test_verifier_detects_control_and_mask_changes(tmp_path):
    lamps = [{'kind': 'AREA', 'location': [0., 0., 2.5], 'target': [0, 0, 0],
              'color': [1, 1, 1], 'power_w': 750., 'size_m': .85,
              'spot_size_rad': .9, 'spot_blend': .25}]
    for kind in ('open', 'outdoor-night', 'indoor'):
        for variant in ('baseline', 'broad', 'soft'):
            job = {'id': 'scene', 'seed': 1, 'treatment': {'lamps': transformed(lamps, variant)}}
            contract = {'jobs_sha256': digest([job])}
            study = {'contract': contract, 'identity': digest(contract), 'jobs': [job]}
            batch = tmp_path / f'{kind}-{variant}'
            scene = batch / 'scenes' / 'scene'
            scene.mkdir(parents=True)
            (batch / 'study.json').write_text(json.dumps(study))
            (scene / 'result.json').write_text('{"status":"accepted"}')
            np.savez(scene / 'masks.npz', visible=np.array([[1, 0]]), full=np.array([[1, 1]]))
    cmd = [sys.executable, str(HERE / 'verify.py'), str(tmp_path), '1']
    assert subprocess.run(cmd, capture_output=True).returncode == 0
    path = tmp_path / 'open-broad/scenes/scene/masks.npz'
    np.savez(path, visible=np.array([[0, 0]]), full=np.array([[1, 1]]))
    assert subprocess.run(cmd, capture_output=True).returncode != 0


def test_postprocessor_recognizes_round3_and_requires_matching_verifier():
    import importlib.util
    spec = importlib.util.spec_from_file_location('lighting_postprocessor', HERE.parent / 'postprocess.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.study_layout(('round3',)) == (('open', 'outdoor-night', 'indoor'), ('baseline', 'broad', 'soft'))
    assert module.study_layout(('round2',)) == (('outdoor-night', 'indoor'), ('baseline', 'soft', 'soft-fill'))
    assert 'if not verifier_matches_bundle: warnings.append' in (HERE.parent / 'postprocess.py').read_text()
    assert 'data.variants' in (HERE.parent / 'gallery.html').read_text()
    assert 'data.conditions' in (HERE.parent / 'gallery.html').read_text()
