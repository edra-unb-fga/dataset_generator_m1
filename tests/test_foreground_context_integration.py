import numpy as np
import pytest

from dataset_generator_m1.generator import _annotation_record
from dataset_generator_m1.models import ForegroundContextConfig
from dataset_generator_m1.scene import SceneRenderer
from test_scene_occlusion import setup_scene


@pytest.mark.parametrize('family', ['landing-pad', 'landing', 'manometro'])
def test_context_changes_rgb_not_geometry_masks_or_labels(family):
    resolved, plan, bg = setup_scene(count=1, family=family)
    context = ForegroundContextConfig(probability=1, strength=(1, 1), radius_fraction=.2,
                                      max_brightness_shift=1, max_color_shift=1)
    scene = resolved.profile.scene.model_copy(update={'foreground_context': context})
    selected = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': scene})})
    old = SceneRenderer(resolved).render(plan, bg)
    new = SceneRenderer(selected).render(plan, bg)
    repeat = SceneRenderer(selected).render(plan, bg)
    assert not np.array_equal(old.image, new.image)
    assert np.array_equal(new.image, repeat.image)
    assert [_annotation_record(a) for a in old.annotations] == [_annotation_record(a) for a in new.annotations]
    assert old.rejected_instances == new.rejected_instances
    assert all(np.array_equal(a, b) for a, b in zip(old.full_coverages + old.visible_coverages,
                                                     new.full_coverages + new.visible_coverages))
    assert new.scene_effects['foreground_context'] == repeat.scene_effects['foreground_context']
    assert new.scene_effects['foreground_context']['objects'][0]['object_attempt'] == plan.instances[0].object_attempt
    assert 'foreground_context' in new.exclusive_timings_ns


def test_disabled_context_has_no_pixel_or_evidence_change():
    resolved, plan, bg = setup_scene()
    disabled = ForegroundContextConfig(probability=0)
    scene = resolved.profile.scene.model_copy(update={'foreground_context': disabled})
    variant = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': scene})})
    old, new = SceneRenderer(resolved).render(plan, bg), SceneRenderer(variant).render(plan, bg)
    assert np.array_equal(old.image, new.image)
    assert old.scene_effects == new.scene_effects


def test_context_configuration_serialization_and_overrides():
    from dataset_generator_m1.config import load_profile
    base = load_profile('examples/configs/landing-pad_minimal.yaml')
    assert 'foreground_context' not in base.profile.scene.model_dump(mode='json')
    selected = load_profile('examples/configs/landing-pad_minimal.yaml',
                            overrides={'scene.foreground_context.probability': 1.0})
    assert selected.profile.scene.foreground_context.probability == 1.0
    assert selected.profile.scene.model_dump(mode='json')['foreground_context']['probability'] == 1.0
    with pytest.raises(ValueError, match='Unknown override path'):
        load_profile('examples/configs/landing-pad_minimal.yaml',
                     overrides={'scene.foreground_context.unknown': 1})
