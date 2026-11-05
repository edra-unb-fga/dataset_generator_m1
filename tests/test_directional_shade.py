import numpy as np
import pytest

from dataset_generator_m1.models import DirectionalShadeConfig, SceneLightingConfig
from dataset_generator_m1.surface_effects import apply_scene_lighting, sample_directional_shade


def test_directional_shade_is_opt_in_and_deterministic():
    lighting = SceneLightingConfig()
    assert 'directional_shade' not in lighting.model_dump(mode='json')
    for config in (DirectionalShadeConfig(probability=0), DirectionalShadeConfig(strength=(0, 0))):
        assert SceneLightingConfig(directional_shade=config).model_dump(mode='json') == lighting.model_dump(mode='json')
        assert sample_directional_shade(config, np.random.default_rng(3)) is None
    config = DirectionalShadeConfig(probability=1)
    assert sample_directional_shade(config, np.random.default_rng(42)) == sample_directional_shade(config, np.random.default_rng(42))
    assert sample_directional_shade(config, np.random.default_rng(42)) != sample_directional_shade(config, np.random.default_rng(43))


@pytest.mark.parametrize('params', [{'strength': [-.1, .5]}, {'strength': [.2, .9]},
    {'width': [0, .2]}, {'width': [.2, .1]}, {'softness': [0, .6]},
    {'offset': [-1.1, 0]}, {'angle_degrees': [0, 361]}, {'probability': float('nan')}])
def test_directional_shade_rejects_invalid_values(params):
    with pytest.raises(ValueError):
        DirectionalShadeConfig.model_validate(params)


def test_hard_and_soft_edges_follow_scene_homography():
    rgb = np.full((64, 64, 3), 180, np.uint8)
    shade = {'applied': True, 'angle': 0., 'offset': 0., 'width': .25, 'softness': 0., 'strength': .6}
    hard = apply_scene_lighting(rgb, np.eye(3), (64, 64), None, directional_shade=shade)
    assert hard[32, 32, 0] < 130 and hard[32, 10, 0] == 180
    assert len(np.unique(hard)) == 2
    soft = apply_scene_lighting(rgb, np.eye(3), (64, 64), None, directional_shade={**shade, 'softness': .125})
    assert len(np.unique(soft)) > 2
    transform = np.array([[1., 0., 11.], [0., 1., 0.], [0., 0., 1.]])
    shifted = apply_scene_lighting(rgb, transform, (64, 64), None, directional_shade=shade)
    assert np.array_equal(hard[:, :53], shifted[:, 11:])
    rotated = np.array([[0., -1., 63.], [1., 0., 0.], [0., 0., 1.]])
    actual = apply_scene_lighting(rgb, rotated, (64, 64), None, directional_shade=shade)
    assert np.array_equal(actual, np.rot90(hard, -1))


@pytest.mark.parametrize('shape', ['band', 'rectangle', 'ellipse'])
def test_renderer_preserves_masks_geometry_and_existing_light_draws(shape):
    from dataset_generator_m1.assets import build_asset_catalog
    from dataset_generator_m1.backgrounds import BackgroundSynthesizer
    from dataset_generator_m1.models import AppearanceConfig
    from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
    from test_scene_contract import small_resolved
    original = small_resolved()
    lighting = SceneLightingConfig(probability=1)
    profile = original.profile.model_copy(update={'scene': original.profile.scene.model_copy(update={'lighting': lighting}), 'appearance': AppearanceConfig()})
    base = original.model_copy(update={'profile': profile})
    catalog = build_asset_catalog(base)
    plan = ScenePlanner(base, catalog).plan(0, 0)
    background = BackgroundSynthesizer(catalog, base.recipes).synthesize(plan.recipe_id, plan.canvas_size, np.random.default_rng(2))
    control = SceneRenderer(base).render(plan, background)
    shade = DirectionalShadeConfig(probability=1, shape=shape, strength=(.7, .7), width=(.8, .8), length=(1, 1), longitudinal_offset=(0, 0), offset=(0, 0), softness=(0, 0))
    scene = profile.scene.model_copy(update={'lighting': lighting.model_copy(update={'directional_shade': shade})})
    treatment = base.model_copy(update={'profile': profile.model_copy(update={'scene': scene})})
    assert plan.geometry_signature() == ScenePlanner(treatment, catalog).plan(0, 0).geometry_signature()
    result = SceneRenderer(treatment).render(plan, background)
    assert [item.bbox for item in control.annotations] == [item.bbox for item in result.annotations]
    assert all(np.array_equal(x, y) for x, y in zip(control.full_coverages, result.full_coverages))
    assert all(np.array_equal(x, y) for x, y in zip(control.visible_coverages, result.visible_coverages))
    assert control.scene_effects['lighting'] == {k: v for k, v in result.scene_effects['lighting'].items() if k != 'directional_shade'}
    assert not np.array_equal(control.image, result.image)
    disabled = scene.model_copy(update={'lighting': lighting.model_copy(update={'directional_shade': DirectionalShadeConfig(probability=0)})})
    off = base.model_copy(update={'profile': profile.model_copy(update={'scene': disabled})})
    repeat = SceneRenderer(off).render(plan, background)
    assert np.array_equal(control.image, repeat.image)
    assert control.scene_effects == repeat.scene_effects


def test_inline_directional_override_preserves_unset_settings_and_can_disable(tmp_path):
    import yaml
    from helpers import write_derived_composer
    from dataset_generator_m1.config import load_profile
    path = write_derived_composer(tmp_path, 'landing-pad', {'scene': {'lighting': {
        'probability': .4, 'gain': [.9, 1.], 'directional_shade': {
            'probability': 1, 'strength': [.4, .6], 'width': [.2, .3], 'softness': [0, .04],
            'offset': [-.1, .1], 'angle_degrees': [0, 90]}}}})
    raw = yaml.safe_load(path.read_text())
    raw['inline'] = {'scene': {'lighting': {'directional_shade': {'probability': 0}}}}
    path.write_text(yaml.safe_dump(raw))
    resolved = load_profile(path)
    light = resolved.profile.scene.lighting
    assert light.probability == .4 and light.gain == (.9, 1.)
    assert light.directional_shade.probability == 0
    assert light.directional_shade.width == (.2, .3)
    assert 'directional_shade' not in light.model_dump(mode='json')
    assert resolved.reference_graph['scene']['inline']['lighting'] == {'directional_shade': {'probability': 0}}


@pytest.mark.parametrize(('field', 'minimum', 'maximum'), [
    ('strength', 0, .8), ('width', .01, 1.5), ('softness', 0, .5),
    ('offset', -1, 1), ('angle_degrees', -360, 360),
])
def test_directional_shade_schema_element_bounds_match_runtime(field, minimum, maximum):
    from dataset_generator_m1.config import generated_json_schemas
    schemas = generated_json_schemas()
    for name in ('composer', 'resolved-profile'):
        spec = schemas[name]['$defs']['DirectionalShadeConfig']['properties'][field]
        assert spec['minItems'] == spec['maxItems'] == 2
        for item in spec['prefixItems']:
            assert item['type'] == 'number'
            assert item['minimum'] == minimum and item['maximum'] == maximum
        # Check both positions at each boundary and just beyond it. Both elements
        # are independently constrained in the published schema.
        for pos in range(2):
            for value, valid in ((minimum, True), (maximum, True),
                                 (minimum - .001, False), (maximum + .001, False)):
                values = [minimum if pos else maximum] * 2
                values[pos] = value
                # Valid pairs must also be ordered; use the opposite extreme in
                # the other position, which leaves out-of-bounds values invalid.
                if valid:
                    values = [value, value]
                schema_accepts = all(rule['minimum'] <= v <= rule['maximum']
                                     for rule, v in zip(spec['prefixItems'], values))
                try:
                    DirectionalShadeConfig.model_validate({field: values})
                    runtime_accepts = True
                except ValueError:
                    runtime_accepts = False
                assert schema_accepts == runtime_accepts == valid
        # Cross-item ordering is a separate runtime invariant, not expressible
        # by ordinary draft 2020-12 array constraints.
        reversed_values = [maximum, minimum]
        assert all(rule['minimum'] <= v <= rule['maximum']
                   for rule, v in zip(spec['prefixItems'], reversed_values))
        with pytest.raises(ValueError, match='ordered'):
            DirectionalShadeConfig.model_validate({field: reversed_values})


@pytest.mark.parametrize('shape', ['rectangle', 'ellipse'])
def test_finite_shapes_are_bounded_soft_and_follow_homography(shape):
    rgb = np.full((64, 64, 3), 180, np.uint8)
    config = DirectionalShadeConfig(probability=1, shape=shape, strength=(.7, .7),
        width=(.3, .3), length=(.5, .5), offset=(0, 0),
        longitudinal_offset=(0, 0), angle_degrees=(0, 0), softness=(0, 0))
    shade = sample_directional_shade(config, np.random.default_rng(42))
    assert shade == sample_directional_shade(config, np.random.default_rng(42))
    assert shade['shape'] == shape
    hard = apply_scene_lighting(rgb, np.eye(3), (64, 64), None, directional_shade=shade)
    assert hard[32, 32, 0] < 120 and hard[0, 32, 0] == 180 and hard[32, 0, 0] == 180
    soft = apply_scene_lighting(rgb, np.eye(3), (64, 64), None, directional_shade={**shade, 'softness': .08})
    assert len(np.unique(soft)) > 2
    transform = np.array([[1., 0., 11.], [0., 1., 0.], [0., 0., 1.]])
    shifted = apply_scene_lighting(rgb, transform, (64, 64), None, directional_shade=shade)
    assert np.array_equal(hard[:, :53], shifted[:, 11:])
    rotated = np.array([[0., -1., 63.], [1., 0., 0.], [0., 0., 1.]])
    assert np.array_equal(apply_scene_lighting(rgb, rotated, (64, 64), None, directional_shade=shade), np.rot90(hard, -1))
    assert DirectionalShadeConfig.model_validate(config.model_dump()).shape == shape


def test_default_band_preserves_existing_serialization_and_sampling():
    config = DirectionalShadeConfig(probability=1)
    assert not {'shape', 'length', 'longitudinal_offset'} & config.model_dump().keys()
    evidence = sample_directional_shade(config, np.random.default_rng(42))
    assert not {'shape', 'length', 'longitudinal_offset'} & evidence.keys()
    with pytest.raises(ValueError):
        DirectionalShadeConfig(shape='ellipse', length=(.5, .1))


def test_mixed_shapes_are_seeded_weighted_and_render_wall():
    config = DirectionalShadeConfig(probability=1, shape='mixed', shape_weights=(0, 0, 0, 1),
        strength=(.5, .5), softness=(0, 0), angle_degrees=(0, 0), offset=(0, 0))
    shade = sample_directional_shade(config, np.random.default_rng(10))
    assert shade['shape'] == 'wall'
    assert shade == sample_directional_shade(config, np.random.default_rng(10))
    image = apply_scene_lighting(np.full((64, 64, 3), 180, np.uint8), np.eye(3), (64, 64), None, directional_shade=shade)
    assert image[32, 10, 0] < image[32, 54, 0]
    with pytest.raises(ValueError):
        DirectionalShadeConfig(shape='mixed', shape_weights=(0, 0, 0, 0))
    with pytest.raises(ValueError):
        DirectionalShadeConfig(shape='mixed', shape_weights=(-1, 1, 1, 1))


def test_guided_coherent_choice_selects_experimental_profiles(tmp_path):
    from rich.console import Console
    from dataset_generator_m1.configurator import default_composer
    from dataset_generator_m1.guided_start import _advanced_editor
    answers = iter(['coherent', 'yes', 'done'])
    document = default_composer('landing')
    result = _advanced_editor(document, tmp_path / 'composer.yaml', Console(quiet=True), lambda *a, **k: next(answers))
    assert result['scene'] == 'builtin:scene/coherent-varied'
    assert result['appearance']['preset'] == 'builtin:appearance/coherent-varied'


def test_guided_coherent_choice_selects_gauge_motion_override(tmp_path):
    from rich.console import Console
    from dataset_generator_m1.configurator import default_composer
    from dataset_generator_m1.guided_start import _advanced_editor
    answers = iter(['coherent', 'yes', 'done'])
    document = default_composer('manometro')
    result = _advanced_editor(document, tmp_path / 'composer.yaml', Console(quiet=True), lambda *a, **k: next(answers))
    assert result['scene'] == 'builtin:scene/coherent-varied'
    assert result['appearance']['preset'] == 'builtin:appearance/coherent-varied-manometro'
    assert default_composer('manometro')['appearance']['preset'] == 'builtin:appearance/realistic-heavy'


def test_manometro_candidate_is_opt_in_and_only_restricts_motion():
    from pathlib import Path
    from dataset_generator_m1.config import load_appearance_profile
    reference = Path('examples/configs/manometro_minimal.yaml')
    general = load_appearance_profile('builtin:appearance/coherent-varied', reference)
    gauge = load_appearance_profile('builtin:appearance/coherent-varied-manometro', reference)
    assert general.foreground == gauge.foreground
    assert [effect.id for effect in general.final] == [effect.id for effect in gauge.final]
    for original, override in zip(general.final, gauge.final):
        if original.id == 'coherent-motion':
            assert (original.probability, override.probability) == (.2, .05)
            assert override.params['blur_limit'] == [3, 3]
        else:
            assert original == override
