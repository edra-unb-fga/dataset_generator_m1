"""Only the newly introduced legacy compositing default is omitted from old hashes."""
import hashlib
import json
from types import SimpleNamespace

import pytest
import yaml

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.identities import digest
from dataset_generator_m1.renderer_version import derived_profile_payload


def legacy_payload(profile):
    result = profile.model_dump(mode='json')
    assert result['scene']['foreground_resampling'] == 'legacy'
    result['scene'].pop('compositing')
    return result


def test_derived_payload_elides_only_new_default_and_does_not_mutate():
    profile = load_profile('examples/configs/landing-pad_minimal.yaml').profile
    original = profile.model_dump(mode='json')
    assert derived_profile_payload(original) == legacy_payload(profile)
    assert original['scene']['compositing'] == 'legacy'
    altered = profile.model_copy(update={'scene':profile.scene.model_copy(update={'compositing':'linear-srgb'})})
    assert derived_profile_payload(altered.model_dump(mode='json'))['scene']['compositing'] == 'linear-srgb'


def test_preview_variant_hash_preserves_historical_payload(tmp_path, monkeypatch):
    from dataset_generator_m1 import workflows
    base = load_profile('examples/configs/landing-pad_minimal.yaml')
    captured = {}
    monkeypatch.setattr(workflows, 'generate_pool', lambda resolved, path, options: captured.setdefault(path.name, resolved.contract_hash))
    variants = tmp_path/'variants.yaml'
    variants.write_text(yaml.safe_dump({'schema_version':1, 'variants':{'legacy':{}, 'linear':{'scene':{'compositing':'linear-srgb'}}}}))
    workflows.preview_scenes('examples/configs/landing-pad_minimal.yaml', variants, tmp_path/'preview', samples=2)
    profile = legacy_payload(base.profile)
    profile['run'] = {**profile['run'], 'label': f'{base.profile.run.label}-legacy', 'num_images':2}
    profile['report'] = {**profile['report'], 'qa_samples':2}
    expected = hashlib.sha256(json.dumps({'base':base.contract_hash, 'variant':'legacy', 'profile':profile}, sort_keys=True).encode()).hexdigest()
    assert captured['legacy'] == expected
    profile['scene']['compositing'] = 'linear-srgb'
    profile['run']['label'] = f'{base.profile.run.label}-linear'
    expected_linear = hashlib.sha256(json.dumps({'base':base.contract_hash, 'variant':'linear', 'profile':profile}, sort_keys=True).encode()).hexdigest()
    assert captured['linear'] == expected_linear


@pytest.mark.parametrize('mode', ['legacy', 'linear-srgb'])
def test_execution_benchmark_hash_uses_historical_legacy_payload(tmp_path, monkeypatch, mode):
    from dataset_generator_m1 import execution_benchmark as bench
    base = load_profile('examples/configs/landing-pad_minimal.yaml', overrides={'scene.compositing':mode})
    plan = SimpleNamespace(workers=1, as_dict=lambda:{})
    captured = []
    monkeypatch.setattr(bench, 'plan_execution', lambda *a, **kw:plan)
    monkeypatch.setattr(bench, 'build_asset_catalog', lambda *a:None)
    def prepare(request):
        captured.append(request.resolved)
        request.output_dir.parent.mkdir(parents=True, exist_ok=True)
        return object()
    monkeypatch.setattr(bench, 'prepare_generation', prepare)
    monkeypatch.setattr(bench, 'generate_pool', lambda *a, **kw:{'status':'complete','elapsed_seconds':1.,'accepted_samples':2,
        'candidate_attempts':2,'throughput_images_per_second':2.,'stage_timings':{},'resource_peaks':{}})
    monkeypatch.setattr(bench, 'inspect_pool', lambda *a:{'status':'valid'})
    monkeypatch.setattr(bench, '_signature', lambda *a:'same')
    monkeypatch.setattr(bench, 'generation_identity', lambda *a:{})
    monkeypatch.setattr(bench, 'software_identity', lambda:{})
    bench.production_benchmark(base, tmp_path/f'bench-{mode}', samples=2, repeats=1, warmup=0)
    profile = base.profile.model_dump(mode='json')
    profile['run']['num_images'] = 2
    if mode == 'legacy':
        profile['scene'].pop('compositing')
    assert profile['scene']['foreground_resampling'] == 'legacy'
    assert captured[0].contract_hash == digest({'base':base.contract_hash, 'benchmark_profile':profile})
