import numpy as np
import pytest

from dataset_generator_m1.models import EnvironmentalShadeConfig, SceneLightingConfig
from dataset_generator_m1.surface_effects import apply_scene_lighting, sample_environmental_shade, sample_lighting


def test_shade_is_opt_in_disabled_serialization_and_seed_independent():
    baseline = SceneLightingConfig()
    expected = {'probability': .8, 'gain': [.85, 1.1], 'gradient': [.05, .25],
                'tint': .025, 'source_assumption': 'unknown'}
    assert baseline.model_dump(mode='json') == expected
    for shade in (EnvironmentalShadeConfig(probability=0), EnvironmentalShadeConfig(strength=(0, 0))):
        assert SceneLightingConfig(shade=shade).model_dump(mode='json') == expected
        assert sample_environmental_shade(shade, np.random.default_rng(2)) is None
    configured = SceneLightingConfig(shade=EnvironmentalShadeConfig(probability=1))
    assert sample_lighting(baseline, np.random.default_rng(11)) == sample_lighting(configured, np.random.default_rng(11))
    a = sample_environmental_shade(configured.shade, np.random.default_rng(41))
    b = sample_environmental_shade(configured.shade, np.random.default_rng(41))
    assert a == b and a['applied']
    assert configured.model_dump(mode='json')['shade']['probability'] == 1


def test_shade_uses_same_scene_homography_and_is_linear_rgb():
    rgb = np.full((48, 64, 3), 160, np.uint8)
    shade = {'applied': True, 'center': [.32, .46], 'radius': [.2, .3], 'angle': .37, 'strength': .6}
    a = apply_scene_lighting(rgb, np.eye(3), (64, 48), None, shade)
    assert a.min() < 120 and a.max() <= 160
    translated = np.array([[1., 0, 16], [0, 1, 0], [0, 0, 1]])
    b = apply_scene_lighting(rgb, translated, (64, 48), None, shade)
    assert np.array_equal(a[:, :48], b[:, 16:])
    clockwise = np.array([[0., -1, 47], [1, 0, 0], [0, 0, 1]])
    c = apply_scene_lighting(np.rot90(rgb, -1), clockwise, (64, 48), None, shade)
    assert np.array_equal(c, np.rot90(a, -1))
    assert np.array_equal(rgb, apply_scene_lighting(rgb, np.eye(3), (64, 48), None,
                                                   {**shade, 'strength': 0}))


def test_shade_workspaces_are_bounded_by_rows(monkeypatch):
    from dataset_generator_m1 import surface_effects
    shapes = []
    convert = surface_effects.srgb_to_linear
    def record(array):
        shapes.append(array.shape)
        return convert(array)
    monkeypatch.setattr(surface_effects, 'srgb_to_linear', record)
    shade = {'applied': True, 'center': [.5, .5], 'radius': [.2, .3], 'angle': 0, 'strength': .4}
    result = apply_scene_lighting(np.full((513, 100, 3), 160, np.uint8), np.eye(3),
                                  (100, 513), None, shade)
    assert result.shape == (513, 100, 3)
    assert len(shapes) == 5 and max(x[0] for x in shapes) == 128


@pytest.mark.parametrize('params', [{'strength': [-.1, .2]}, {'strength': [.2, .9]},
                                    {'radius_fraction': [.01, .2]}, {'radius_fraction': [.5, .2]},
                                    {'probability': float('nan')}])
def test_shade_rejects_unbounded_or_invalid_values(params):
    with pytest.raises(ValueError):
        EnvironmentalShadeConfig.model_validate(params)



def test_renderer_shade_keeps_masks_lighting_draws_and_capture_order():
    from dataset_generator_m1.assets import build_asset_catalog
    from dataset_generator_m1.backgrounds import BackgroundSynthesizer
    from dataset_generator_m1.filters import apply_pipeline_traced
    from dataset_generator_m1.models import AppearanceConfig, TransformSpec
    from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
    from test_scene_contract import small_resolved
    original = small_resolved()
    lighting = SceneLightingConfig(probability=1, gain=(.9, .9), gradient=(.1, .1), tint=.01)
    profile = original.profile.model_copy(update={'scene': original.profile.scene.model_copy(update={'lighting': lighting}),
                                                  'appearance': AppearanceConfig()})
    base = original.model_copy(update={'profile': profile})
    catalog = build_asset_catalog(base)
    plan = ScenePlanner(base, catalog).plan(0, 0)
    background = BackgroundSynthesizer(catalog, base.recipes).synthesize(plan.recipe_id, plan.canvas_size,
                                                                       np.random.default_rng(2))
    a = SceneRenderer(base).render(plan, background)
    shade = EnvironmentalShadeConfig(probability=1, strength=(.6, .6), radius_fraction=(.8, .8))
    scene = profile.scene.model_copy(update={'lighting': lighting.model_copy(update={'shade': shade})})
    shaded = base.model_copy(update={'profile': profile.model_copy(update={'scene': scene})})
    assert plan.geometry_signature() == ScenePlanner(shaded, catalog).plan(0, 0).geometry_signature()
    b = SceneRenderer(shaded).render(plan, background)
    assert [item.bbox for item in a.annotations] == [item.bbox for item in b.annotations]
    assert all(np.array_equal(x, y) for x, y in zip(a.full_coverages, b.full_coverages))
    assert all(np.array_equal(x, y) for x, y in zip(a.visible_coverages, b.visible_coverages))
    assert a.scene_effects['lighting'] == {key: value for key, value in b.scene_effects['lighting'].items() if key != 'shade'}
    assert not np.array_equal(a.image, b.image)
    spec = TransformSpec(type='RandomBrightnessContrast', id='capture', probability=1,
                         params={'brightness_limit': [-.1, -.1], 'contrast_limit': [0., 0.]})
    captured = shaded.model_copy(update={'profile': shaded.profile.model_copy(update={'appearance': AppearanceConfig(final=(spec,))})})
    c = SceneRenderer(captured).render(plan, background)
    expected, _ = apply_pipeline_traced(b.image, (spec,), 1, 'final')
    assert np.array_equal(c.image, expected)
    disabled = scene.model_copy(update={'lighting': lighting.model_copy(update={'shade': EnvironmentalShadeConfig(probability=0)})})
    off = base.model_copy(update={'profile': profile.model_copy(update={'scene': disabled})})
    d = SceneRenderer(off).render(plan, background)
    assert np.array_equal(a.image, d.image)
    assert a.scene_effects == d.scene_effects



@pytest.mark.parametrize('disabled', [{'probability': 0}, {'strength': [0, 0]}])
def test_inline_disabled_shade_overrides_enabled_profile_and_renders_unshaded(tmp_path, disabled):
    import yaml
    from helpers import write_derived_composer
    from dataset_generator_m1.assets import build_asset_catalog
    from dataset_generator_m1.backgrounds import BackgroundSynthesizer
    from dataset_generator_m1.config import load_profile
    from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
    lighting = SceneLightingConfig(shade=EnvironmentalShadeConfig(probability=1, strength=(.6, .6),
                                                                  radius_fraction=(.8, .8)))
    path = write_derived_composer(tmp_path, 'landing-pad', {
        'scene': {'lighting': lighting.model_dump(mode='json')},
        'output': {'image_size': [128, 96], 'image_format': 'png'}})
    raw = yaml.safe_load(path.read_text())
    raw['appearance'] = {'preset': 'builtin:appearance/no-appearance'}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    enabled = load_profile(path)
    raw['inline'] = {'scene': {'lighting': {'shade': disabled}}}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    off = load_profile(path)
    shade = off.profile.scene.lighting.shade
    assert shade is not None
    assert shade.probability == 0 if 'probability' in disabled else shade.strength == (0, 0)
    assert 'shade' not in off.profile.scene.lighting.model_dump(mode='json')
    assert off.reference_graph['scene']['inline']['lighting']['shade'].items() >= disabled.items()
    # An explicit unshaded resolved profile establishes the expected pixel result.
    unshaded = off.model_copy(update={'profile': off.profile.model_copy(update={
        'scene': off.profile.scene.model_copy(update={'lighting': off.profile.scene.lighting.model_copy(update={'shade': None})})})})
    catalog = build_asset_catalog(off)
    plan = ScenePlanner(off, catalog).plan(0, 0)
    assert plan.geometry_signature() == ScenePlanner(enabled, catalog).plan(0, 0).geometry_signature()
    background = BackgroundSynthesizer(catalog, off.recipes).synthesize(plan.recipe_id, plan.canvas_size,
                                                                       np.random.default_rng(2))
    baseline = SceneRenderer(unshaded).render(plan, background)
    actual = SceneRenderer(off).render(plan, background)
    shaded = SceneRenderer(enabled).render(plan, background)
    assert np.array_equal(actual.image, baseline.image)
    assert actual.scene_effects == baseline.scene_effects
    assert not np.array_equal(actual.image, shaded.image)
    assert all(np.array_equal(x, y) for x, y in zip(actual.full_coverages, shaded.full_coverages))
    assert all(np.array_equal(x, y) for x, y in zip(actual.visible_coverages, shaded.visible_coverages))
