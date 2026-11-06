import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'experiments/foreground-context/coherent-study/scaled_review.py'
spec = importlib.util.spec_from_file_location('scaled_review_panel', SCRIPT)
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


def test_review_panel_fixed_and_scaled_profiles_keep_paired_scene_controls(tmp_path):
    for index, (kind, kernel) in enumerate(panel.CASES):
        fixed = panel.profile(tmp_path, 'manometro', 'fixed', 640, index, 1234 + index).profile
        scaled = panel.profile(tmp_path, 'manometro', 'scaled', 640, index, 1234 + index).profile
        assert fixed.scene == scaled.scene
        assert fixed.sampling == scaled.sampling
        assert fixed.assets == scaled.assets
        assert fixed.assets.backgrounds.group_weights == {panel.GROUPS[index]: 1.0}
        first = next(e for e in fixed.appearance.final if e.type == 'WeightedMotionBlur')
        second = next(e for e in scaled.appearance.final if e.type == 'WeightedMotionBlur')
        assert 'reference_size' not in first.params
        assert second.params['reference_size'] == 640
        assert first.probability == second.probability
        if kernel:
            assert first.params['kernels'] == second.params['kernels'] == [kernel]
        if kernel == 0:
            assert first.probability == 0
    assert len(panel.CASES) == 8
    assert len(set(panel.GROUPS)) >= 6


def test_cross_resolution_comparison_rejects_misaligned_targets_and_sources():
    from copy import deepcopy
    small = {'scene_to_output': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
             'background': {'sources': [{'content_hash': 'background'}]},
             'annotations': [{'instance_id': 'a', 'source_content_hash': 'target',
                 'asset_to_output': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'bbox': [10, 20, 30, 40]}]}
    large = deepcopy(small)
    large['annotations'][0]['asset_to_output'] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    large['annotations'][0]['bbox'] = [20, 40, 60, 80]
    assert panel.cross_resolution_evidence(small, large, 'landing', 0)['status'] == 'pass'
    large['annotations'][0]['asset_to_output'][0][2] = 3
    assert panel.cross_resolution_evidence(small, large, 'landing', 0)['status'] == 'review-needed'
    large['annotations'][0]['asset_to_output'][0][2] = 0
    large['background']['sources'][0]['content_hash'] = 'changed'
    assert panel.cross_resolution_evidence(small, large, 'landing', 0)['status'] == 'review-needed'


def test_review_gallery_bundle_contains_profiles_and_crop_hashes(tmp_path):
    import hashlib
    import json
    import zipfile
    from PIL import Image
    from package_review_gallery import package

    study = tmp_path / 'study'
    pool = study / 'case'
    pool.mkdir(parents=True)
    image = pool / 'image.png'
    Image.new('RGB', (32, 32), (23, 45, 67)).save(image)
    (study / 'profiles').mkdir()
    (study / 'profiles/case.json').write_text(json.dumps({'profile': {'seed': 1}}))
    record = {'family': 'landing-pad', 'case': 0, 'kind': 'forced-mild',
              'configured_kernel': 3, 'shade_forced': True, 'size_stratum': 'small',
              'size': 640, 'variant': 'scaled', 'seed': 1, 'source_group': 'grass',
              'signature': 'fixture', 'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
              'pool': 'case', 'image_path': 'image.png', 'profile_path': 'profiles/case.json',
              'sample': {'annotations': [{'bbox': [5, 6, 20, 21]}]}}
    (study / 'records.json').write_text(json.dumps([record]))
    gallery = tmp_path / 'gallery'
    panel.make_gallery(study, gallery)
    manifest = json.loads((gallery / 'manifest.json').read_text())
    assert all(x['metadata']['profile_file'] == 'profiles/case.json' for x in manifest['images'])
    crop = next(x for x in manifest['images'] if x['engine'] == '2D crop')
    assert crop['metadata']['image_sha256'] == hashlib.sha256((gallery / crop['path']).read_bytes()).hexdigest()
    assert crop['metadata']['parent_image_sha256'] == record['image_sha256']
    archive = tmp_path / 'review.zip'
    assert package(gallery, archive, tmp_path)['verified']
    with zipfile.ZipFile(archive) as bundle:
        assert 'profiles/case.json' in bundle.namelist()


def test_3d_natural_review_keeps_actual_config_for_bundle(tmp_path):
    import hashlib
    import json
    from PIL import Image

    script = SCRIPT.with_name('curate_3d_review.py')
    module_spec = importlib.util.spec_from_file_location('curate_3d_review', script)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    reviewed = tmp_path / 'reviewed'
    gallery = reviewed / 'gallery'
    gallery.mkdir(parents=True)
    source = gallery / 'source.png'
    Image.new('RGB', (8, 8), (10, 20, 30)).save(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (gallery / 'manifest.json').write_text(json.dumps({'images': [{'path': 'source.png',
        'condition': 'indoor', 'metadata': {'image_sha256': digest, 'job': {'id': '000'}}}]}))
    (reviewed / 'evidence.json').write_text(json.dumps({'complete': True, 'verified': True,
        'provenance_verified': True, 'stop_confirmed': True}))
    config = reviewed / 'recovered/workspace/natural-config.json'
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({'seed': 54321}))
    dest = tmp_path / 'gallery'
    dest.mkdir()
    rows = []
    module.collect_natural(reviewed, dest, 'balanced', rows)
    metadata = rows[0]['metadata']
    assert (dest / metadata['profile_file']).read_bytes() == config.read_bytes()
    assert metadata['profile_source_sha256'] == hashlib.sha256(config.read_bytes()).hexdigest()
