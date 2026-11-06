import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import _annotation_record
from dataset_generator_m1.scene import SceneRenderer
from test_scene_occlusion import setup_scene


@pytest.mark.parametrize('family', ['landing', 'landing-pad', 'manometro'])
@pytest.mark.parametrize('treatment', ['coherent-candidate', 'coherent-refined', 'coherent-directional'])
def test_candidate_is_explicit_and_preserves_geometry_and_annotations(tmp_path, family, treatment):
    source = Path(f'examples/configs/{family}_minimal.yaml')
    raw = yaml.safe_load(source.read_text())
    legacy = load_profile(source)
    raw['scene'] = f'builtin:scene/{treatment}'
    appearance = 'coherent-refined' if treatment == 'coherent-directional' else treatment
    raw['appearance'] = {'preset': f'builtin:appearance/{appearance}'}
    config = tmp_path / 'composer.yaml'
    config.write_text(yaml.safe_dump(raw))
    candidate = load_profile(config)
    assert legacy.profile.scene.foreground_context is None
    assert legacy.profile.scene.lighting is None
    assert candidate.profile.scene.foreground_context.probability == 1
    assert candidate.profile.appearance.foreground[0].type == 'SurfaceWear'
    assert candidate.profile.scene.camera == legacy.profile.scene.camera
    assert candidate.profile.scene.perspective == legacy.profile.scene.perspective
    assert candidate.profile.scene.background_affine == legacy.profile.scene.background_affine

    resolved, plan, bg = setup_scene(count=1, family=family)
    selected = resolved.model_copy(update={'profile': resolved.profile.model_copy(update={
        'scene': candidate.profile.scene, 'appearance': candidate.profile.appearance})})
    baseline = SceneRenderer(resolved).render(plan, bg)
    result = SceneRenderer(selected).render(plan, bg)
    repeated = SceneRenderer(selected).render(plan, bg)
    assert np.array_equal(result.image, repeated.image)
    assert [_annotation_record(a) for a in result.annotations] == [_annotation_record(a) for a in baseline.annotations]
    assert result.rejected_instances == baseline.rejected_instances
    assert all(np.array_equal(a, b) for a, b in zip(result.full_coverages + result.visible_coverages,
                                                     baseline.full_coverages + baseline.visible_coverages))


def test_study_combination_matches_candidate_profile():
    source = Path('src/dataset_generator_m1/profiles/builtin/scene/coherent-candidate/profile.yaml')
    scene = yaml.safe_load(source.read_text())['value']
    matrix = json.loads(Path('experiments/foreground-context/coherent-candidate.json').read_text())
    combined = matrix['variants']['candidate-combined']
    assert combined['context'] == scene['foreground_context']
    assert combined['lighting'] == scene['lighting']
    appearance = yaml.safe_load(Path('src/dataset_generator_m1/profiles/builtin/appearance/coherent-candidate/profile.yaml').read_text())['value']
    assert matrix['variants']['candidate-forced-wear']['wear'] == appearance['foreground'][0]['params']
    assert matrix['seeds']['development'] != matrix['seeds']['reserved']
