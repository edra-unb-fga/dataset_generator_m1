import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def load(name):
    path = Path(__file__).parents[1] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_3d_checks_accepted_image_hash(tmp_path):
    scene = tmp_path / 'results' / 'batch' / 'scenes' / 'job'
    scene.mkdir(parents=True)
    (scene / 'rgb.png').write_bytes(b'pixels')
    result = {'status': 'accepted', 'job': {'environment_geometry': 'indoor'},
              'files': {'rgb.png': hashlib.sha256(b'pixels').hexdigest()}}
    (scene / 'result.json').write_text(json.dumps(result))
    manifest = load('collect_3d_review_gallery').collect(tmp_path / 'results', tmp_path / 'gallery')
    assert len(manifest['images']) == 1
    assert manifest['images'][0]['condition'] == 'indoor'
    result['files']['rgb.png'] = '0' * 64
    (scene / 'result.json').write_text(json.dumps(result))
    with pytest.raises(ValueError, match='checksum'):
        load('collect_3d_review_gallery').collect(tmp_path / 'results', tmp_path / 'invalid')


def test_collect_2d_preserves_sample_and_seed(tmp_path):
    study = tmp_path / 'study'
    pool = study / 'pad-candidate'
    (pool / 'images').mkdir(parents=True)
    (pool / 'images' / 'sample.jpg').write_bytes(b'image')
    (pool / 'samples.jsonl').write_text(json.dumps({'slot': 2, 'image_path': 'images/sample.jpg', 'geometry_signature': 'geometry'}) + '\n')
    (study / 'pad-profiles.json').write_text(json.dumps({'candidate': {'profile': {'run': {'seed': 42}}}}))
    (study / 'records.json').write_text(json.dumps([{'family': 'pad', 'variant': 'candidate', 'pool': 'pad-candidate'}]))
    result = load('collect_2d_review_gallery').collect(study, tmp_path / 'gallery')
    metadata = result['images'][0]['metadata']
    assert metadata['run_seed'] == 42
    assert metadata['sample']['geometry_signature'] == 'geometry'
    assert (tmp_path / 'gallery' / metadata['profile_file']).is_file()


def test_collect_2d_places_matching_baseline_and_candidate_adjacent(tmp_path):
    study = tmp_path / 'study'
    records = []
    for variant in ('candidate', 'baseline'):
        pool = study / variant
        pool.mkdir(parents=True)
        (pool / 'image.jpg').write_bytes(b'image')
        (pool / 'samples.jsonl').write_text(''.join(json.dumps({'slot': slot, 'image_path': 'image.jpg'}) + '\n' for slot in (0, 1)))
        records.append({'family': 'pad', 'variant': variant, 'pool': variant})
    (study / 'records.json').write_text(json.dumps(records))
    result = load('collect_2d_review_gallery').collect(study, tmp_path / 'gallery')
    assert [(x['metadata']['sample']['slot'], x['condition']) for x in result['images']] == [
        (0, 'baseline'), (0, 'candidate'), (1, 'baseline'), (1, 'candidate')]
