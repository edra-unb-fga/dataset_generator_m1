from dataclasses import replace
import cv2
import numpy as np
import pytest

from dataset_generator_m1.filters import apply_pipeline_traced, validate_transform_specs
from dataset_generator_m1.models import TransformSpec, SceneLightingConfig
from dataset_generator_m1.surface_effects import apply_scene_lighting, apply_surface_wear, linear_to_srgb, srgb_to_linear
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer
from test_scene_contract import small_resolved


def test_wear_alpha_seed_and_source_resolution():
    rgb = np.full((256, 512, 3), 170, np.uint8)
    params = {'marks':16,'dirt':.5,'scratches':.3}
    first, small_evidence = apply_surface_wear(rgb, params, np.random.default_rng(42))
    big, big_evidence = apply_surface_wear(np.repeat(np.repeat(rgb,2,0),2,1), params, np.random.default_rng(42))
    assert small_evidence == big_evidence
    difference=np.abs(first.astype(float)-cv2.resize(big,(512,256),interpolation=cv2.INTER_AREA))
    assert difference.mean() < .15 and np.percentile(difference,99) <= 2
    rgba = np.dstack([rgb, np.random.default_rng(1).integers(0,256,rgb.shape[:2],dtype=np.uint8)])
    specs = [TransformSpec(id='wear',type='SurfaceWear',params=params)]
    result, traces = apply_pipeline_traced(rgba,specs,42,'foreground:0',preserve_alpha=True)
    assert np.array_equal(result[:,:,3],rgba[:,:,3])
    assert traces[0].applied_params[0]['local_marks']
    with pytest.raises(ValueError,match='foreground-only'):
        validate_transform_specs(specs,'appearance.final')
    with pytest.raises(ValueError):
        validate_transform_specs([TransformSpec(type='SurfaceWear',params={'marks':65})],'appearance.foreground')


def test_common_field_uses_linear_rgb_and_shared_homography():
    rgb = np.full((48,64,3),128,np.uint8)
    evidence={'applied':True,'gain':.5,'gradient':[0,0],'tint':[0,0,0]}
    result=apply_scene_lighting(rgb,np.eye(3),(64,48),evidence)
    expected=linear_to_srgb(srgb_to_linear(rgb)*.5)
    assert np.array_equal(result,expected) and result[0,0,0]>64
    evidence.update(gain=1.,gradient=[.6,0])
    a=apply_scene_lighting(rgb,np.eye(3),(64,48),evidence)
    translated=np.array([[1.,0,16],[0,1,0],[0,0,1]])
    b=apply_scene_lighting(rgb,translated,(64,48),evidence)
    assert np.array_equal(a[:,:48],b[:,16:])
    assert np.all(a[:,0,0]<a[:,-1,0])


def test_lighting_keeps_geometry_masks_and_runs_before_capture():
    resolved=small_resolved()
    profile=resolved.profile.model_copy(update={'appearance':resolved.profile.appearance.model_copy(update={'background':(),'foreground':(),'final':()})})
    resolved=resolved.model_copy(update={'profile':profile})
    catalog=build_asset_catalog(resolved)
    plan=ScenePlanner(resolved,catalog).plan(0,0)
    bg=BackgroundSynthesizer(catalog,resolved.recipes).synthesize('direct',plan.canvas_size,np.random.default_rng(2))
    a=SceneRenderer(resolved).render(plan,bg)
    lit=resolved.model_copy(update={'profile':profile.model_copy(update={'scene':profile.scene.model_copy(update={'lighting':SceneLightingConfig(probability=1,gain=(.7,.7))})})})
    assert plan.geometry_signature()==ScenePlanner(lit,catalog).plan(0,0).geometry_signature()
    b=SceneRenderer(lit).render(plan,bg)
    assert [x.bbox for x in a.annotations]==[x.bbox for x in b.annotations]
    assert all(np.array_equal(x,y) for x,y in zip(a.instance_masks,b.instance_masks))
    assert not np.array_equal(a.image,b.image)
    assert b.scene_effects['lighting']['gain']==.7


def test_renderer_upgrade_refuses_resume_but_old_pool_inspects(tmp_path):
    import json
    from helpers import write_derived_composer
    from dataset_generator_m1.config import load_profile
    from dataset_generator_m1.generator import generate_pool, GenerationOptions
    from dataset_generator_m1.inspection import inspect_pool
    config=write_derived_composer(tmp_path,'landing-pad',{'run':{'num_images':1},'output':{'image_size':[96,96]},'background_mixing':{'recipe_weights':{'direct':1.}},'reporting':{'qa_samples':0}})
    resolved=load_profile(config)
    pool=tmp_path/'pool'
    generate_pool(resolved,pool,GenerationOptions(display='quiet'))
    assert generate_pool(resolved,pool,GenerationOptions(display='quiet',resume=True))['status']=='complete'
    record=json.loads((pool/'run.json').read_text())
    record.pop('renderer_semantics')
    (pool/'run.json').write_text(json.dumps(record))
    assert inspect_pool(pool)['status']=='valid'
    with pytest.raises(ValueError,match='fresh pool'):
        generate_pool(resolved,pool,GenerationOptions(display='quiet',resume=True))
