"""Experimental linear-light compositing preserves sampling and annotation contracts."""
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import _annotation_record
from dataset_generator_m1.identities import generation_contract
from dataset_generator_m1.imaging import composite_linear_srgb
from dataset_generator_m1.models import SceneConfig, SceneOcclusionConfig
from dataset_generator_m1.renderer_version import contract_profile
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
from dataset_generator_m1.scene_occlusion import SceneOccluder, composite_occluders


def test_srgb_transfer_curve_alpha_extremes_and_bounded_tiles():
    base = np.zeros((257, 2, 3), np.uint8)
    foreground = np.full_like(base, 255)
    alpha = np.full((257, 2), .5, np.float32)
    alpha[0, 0], alpha[0, 1] = 0., 1.
    result = composite_linear_srgb(base, foreground, alpha)
    assert np.array_equal(result[0, 0], [0, 0, 0])
    assert np.array_equal(result[0, 1], [255, 255, 255])
    assert np.all(result[1:] == 188)  # IEC sRGB: encoding(linear 0.5), not 127
    # Exercise the low, linear segment of the true transfer function.
    low = composite_linear_srgb(np.zeros((1, 1, 3), np.uint8), np.full((1, 1, 3), 10, np.uint8), np.full((1, 1), .5, np.float32))
    assert np.all(low == 5)
    # 0 and 1 coverage must preserve every possible 8-bit input exactly.
    values = np.broadcast_to(np.arange(256, dtype=np.uint8)[None, :, None], (1, 256, 3)).copy()
    assert np.array_equal(composite_linear_srgb(values, np.zeros_like(values), np.zeros((1, 256), np.float32)), values)
    assert np.array_equal(composite_linear_srgb(np.zeros_like(values), values, np.ones((1, 256), np.float32)), values)


def test_occluder_uses_same_linear_compositing_without_changing_coverage():
    base = np.zeros((64, 64, 3), np.uint8)
    layer = SceneOccluder('debris', ((4., 4.), (60., 4.), (60., 60.), (4., 60.)), (255, 255, 255), .5)
    legacy, old_mask = composite_occluders(base, (layer,), np.eye(3))
    linear, new_mask = composite_occluders(base, (layer,), np.eye(3), compositing='linear-srgb')
    assert np.array_equal(old_mask, new_mask)
    assert np.all(legacy[32, 32] == 128)
    assert np.all(linear[32, 32] == 188)


def test_contract_legacy_omission_and_explicit_opt_in():
    resolved = load_profile('examples/configs/landing-pad_minimal.yaml')
    legacy = load_profile('examples/configs/landing-pad_minimal.yaml', overrides={'scene.compositing': 'legacy'})
    linear = load_profile('examples/configs/landing-pad_minimal.yaml', overrides={'scene.compositing': 'linear-srgb'})
    assert 'compositing' not in contract_profile(resolved.profile)['scene']
    assert contract_profile(resolved.profile) == contract_profile(legacy.profile)
    catalog = build_asset_catalog(resolved)
    assert generation_contract(resolved, catalog) == generation_contract(legacy, catalog)
    assert generation_contract(resolved, catalog) != generation_contract(linear, catalog)
    with pytest.raises(ValueError):
        SceneConfig(compositing='bogus')


@pytest.mark.parametrize('family', ['landing-pad', 'landing', 'manometro'])
@pytest.mark.parametrize('resampling', ['legacy', 'premultiplied'])
def test_paired_render_retains_geometry_masks_and_effect_choices(family, resampling, tmp_path):
    resolved = load_profile(f'examples/configs/{family}_minimal.yaml', overrides={
        'output.image_size': [192, 128], 'sampling.instances_per_image': [2, 2], 'run.num_images': 1,
        'scene.foreground_resampling': resampling})
    scene = resolved.profile.scene.model_copy(update={'occlusion': SceneOcclusionConfig(probability=1, min_visible_support=0)})
    resolved = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': scene})})
    selected = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': scene.model_copy(update={'compositing': 'linear-srgb'})})})
    catalog = build_asset_catalog(resolved)
    plan = ScenePlanner(resolved, catalog).plan(0, 0)
    paired = ScenePlanner(selected, catalog).plan(0, 0)
    assert plan.geometry_signature() == paired.geometry_signature()
    background = BackgroundSynthesizer(catalog, resolved.recipes).synthesize(plan.recipe_id, plan.canvas_size, np.random.default_rng(4))
    old, new = SceneRenderer(resolved).render(plan, background), SceneRenderer(selected).render(plan, background)
    assert [_annotation_record(v) for v in old.annotations] == [_annotation_record(v) for v in new.annotations]
    assert old.rejected_instances == new.rejected_instances
    assert old.scene_effects == new.scene_effects
    assert [{k: v for k, v in t.items() if k != 'duration_ns'} for t in old.effect_traces] == [{k: v for k, v in t.items() if k != 'duration_ns'} for t in new.effect_traces]
    assert len(old.full_coverages) == len(new.full_coverages)
    for a, b in zip(old.full_coverages + old.visible_coverages, new.full_coverages + new.visible_coverages):
        assert np.array_equal(a, b)
    assert not np.array_equal(old.image, new.image)
    # Feed arbitrary semitransparent RGBA through the real renderer, retaining family metadata.
    rgba = np.zeros((32, 32, 4), np.uint8)
    rgba[:, :, :3] = [220, 30, 70]
    rgba[:, :, 3] = np.arange(32, dtype=np.uint8)[None, :] * 8
    path = tmp_path / 'generic.png'
    Image.fromarray(rgba).save(path)
    instance = replace(plan.instances[0], asset=replace(plan.instances[0].asset, path=path, width=32, height=32))
    generic_plan = replace(plan, instances=(instance,), attempted_instances=1)
    a, b = SceneRenderer(resolved).render(generic_plan, background), SceneRenderer(selected).render(generic_plan, background)
    assert [_annotation_record(v) for v in a.annotations] == [_annotation_record(v) for v in b.annotations]
    assert all(np.array_equal(x, y) for x, y in zip(a.full_coverages + a.visible_coverages, b.full_coverages + b.visible_coverages))


def test_inline_override_precedence_and_preflight_warning(tmp_path):
    import yaml
    from helpers import write_derived_composer
    from dataset_generator_m1.preflight import PreflightRequest, run_preflight
    path = write_derived_composer(tmp_path, 'landing-pad', {
        'scene': {'compositing': 'linear-srgb', 'lighting': {'probability': .4, 'gain': [.7, .8]}}})
    raw = yaml.safe_load(path.read_text())
    raw['inline'] = {'scene': {'compositing': 'legacy'}}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    legacy = load_profile(path)
    assert legacy.profile.scene.compositing == 'legacy'
    assert legacy.profile.scene.lighting.gain == (.7, .8)
    assert legacy.reference_graph['scene']['inline'] == {'compositing': 'legacy'}
    linear = load_profile(path, overrides={'scene.compositing': 'linear-srgb'})
    assert linear.profile.scene.compositing == 'linear-srgb'
    result = run_preflight(PreflightRequest(linear, tmp_path / 'run', workers=1, observation_path=tmp_path / 'observations.jsonl'))
    assert 'EXPERIMENTAL_LINEAR_COMPOSITING_UNVALIDATED' in [w['code'] for w in result['warnings']]
    assert 'compositing-unmeasured' in result['runtime']['confidence']


def test_memory_accounts_for_linear_tile_and_retained_foreground():
    from dataset_generator_m1.memory_planning import memory_components, source_shapes
    resolved = load_profile('examples/configs/landing-pad_minimal.yaml', overrides={'output.image_size': [640, 640], 'scene.compositing': 'linear-srgb'})
    sizes = source_shapes(resolved)
    linear = memory_components(resolved, 1, 1, 1, sizes)
    legacy_scene = resolved.profile.scene.model_copy(update={'compositing': 'legacy'})
    legacy = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': legacy_scene})})
    old = memory_components(legacy, 1, 1, 1, sizes)
    assert linear['phase_peaks_bytes_per_worker']['scene_render'] >= old['phase_peaks_bytes_per_worker']['scene_render']
    assert linear['phase_peaks_bytes_per_worker']['scene_render'] >= 640 * 128 * 160 + 640 * 640 * 8
