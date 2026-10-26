"""Filtering may change RGB, never the legacy geometric alpha path."""

import cv2
import numpy as np
import pytest

from dataset_generator_m1.generator import _annotation_record
from dataset_generator_m1.imaging import resize_rgba, rotate_rgba, warp_rgba
from dataset_generator_m1.renderer_version import contract_profile
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.models import SceneConfig
from dataset_generator_m1.identities import generation_contract
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
from dataset_generator_m1.backgrounds import BackgroundSynthesizer


@pytest.mark.parametrize('mode', ['square', 'circle'])
@pytest.mark.parametrize('alpha', [0, 47, 255])
def test_hidden_rgb_cannot_affect_filtered_visible_color(mode, alpha):
    a = np.zeros((64, 64, 4), np.uint8)
    a[12:52, 12:52] = [220, 30, 20, alpha]
    b = a.copy()
    b[b[:, :, 3] == 0, :3] = [0, 255, 255]
    matrix = np.array([[.93, .07, -4], [-.03, 1.01, 3], [.0004, -.0003, 1.]])
    def operations(image, corrected):
        image = rotate_rgba(image, 17.3, mode, premultiplied=corrected)
        image = resize_rgba(image, 37, premultiplied=corrected)
        return warp_rgba(image, matrix, (53, 49), premultiplied=corrected)
    old, first, second = operations(a, False), operations(a, True), operations(b, True)
    assert np.array_equal(first[:, :, 3], old[:, :, 3])
    assert np.array_equal(first, second)
    assert np.isfinite(first).all()


def test_legacy_filtering_remains_exact_opencv():
    image = np.random.default_rng(31).integers(0, 256, (23, 31, 4), dtype=np.uint8)
    assert np.array_equal(resize_rgba(image, 11), cv2.resize(image, (11, 8), interpolation=cv2.INTER_AREA))
    identity = np.eye(3)
    assert np.array_equal(warp_rgba(image, identity, (31, 23)), image)
    assert np.array_equal(warp_rgba(image, identity, (31, 23), premultiplied=True)[:, :, 3], image[:, :, 3])


def test_only_new_legacy_field_is_elided_from_hash_payload():
    resolved = load_profile('examples/configs/landing-pad_minimal.yaml')
    payload = resolved.profile.model_dump(mode='json')
    payload['scene'].pop('foreground_resampling')
    assert contract_profile(resolved.profile) == payload
    scene = resolved.profile.scene.model_copy(update={'foreground_resampling': 'premultiplied'})
    changed = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': scene})})
    assert contract_profile(changed.profile)['scene']['foreground_resampling'] == 'premultiplied'
    selected = load_profile('examples/configs/landing-pad_minimal.yaml', overrides={'scene.foreground_resampling': 'premultiplied'})
    assert selected.profile.scene.foreground_resampling == 'premultiplied'
    catalog = build_asset_catalog(resolved)
    assert generation_contract(resolved, catalog) != generation_contract(changed, catalog)
    with pytest.raises(ValueError):
        SceneConfig(foreground_resampling='unknown')


@pytest.mark.parametrize('family', ['landing', 'manometro', 'landing-pad'])
def test_corrected_renderer_preserves_plan_masks_boxes_and_visibility(family):
    resolved = load_profile(f'examples/configs/{family}_minimal.yaml', overrides={
        'output.image_size': [192, 128], 'sampling.instances_per_image': [2, 2],
        'run.num_images': 1,
    })
    catalog = build_asset_catalog(resolved)
    scene = resolved.profile.scene.model_copy(update={'foreground_resampling': 'premultiplied'})
    corrected = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={'scene': scene})})
    plan = ScenePlanner(resolved, catalog).plan(0, 0)
    other = ScenePlanner(corrected, catalog).plan(0, 0)
    assert plan.geometry_signature() == other.geometry_signature()
    bg = BackgroundSynthesizer(catalog, resolved.recipes).synthesize(plan.recipe_id, plan.canvas_size, np.random.default_rng(4))
    a = SceneRenderer(resolved).render(plan, bg)
    b = SceneRenderer(corrected).render(plan, bg)
    assert [_annotation_record(v) for v in a.annotations] == [_annotation_record(v) for v in b.annotations]
    assert a.rejected_instances == b.rejected_instances
    for old, new in zip(a.full_coverages + a.visible_coverages, b.full_coverages + b.visible_coverages):
        assert np.array_equal(old, new)
