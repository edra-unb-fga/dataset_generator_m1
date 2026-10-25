from dataclasses import replace
import json

import numpy as np
import pytest

from dataset_generator_m1.annotation_evidence import visible_coverages
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSample
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.models import AppearanceConfig, OutputConfig, SceneOcclusionConfig, SamplingConfig
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer, SceneRejected
from dataset_generator_m1.scene_occlusion import SceneOccluder, composite_occluders


def setup_scene(count=1, floor=.25):
    resolved=load_profile('examples/configs/landing-pad_minimal.yaml')
    profile=resolved.profile.model_copy(update={'output':OutputConfig(image_size=(128,128)),
        'appearance':AppearanceConfig(), 'sampling':SamplingConfig(instances_per_image=(count,count),foreground_size=(.3,.3),min_visible_bbox_fraction=.01),
        'scene':resolved.profile.scene.model_copy(update={'occlusion':SceneOcclusionConfig(probability=1,min_visible_support=floor)})})
    resolved=resolved.model_copy(update={'profile':profile})
    catalog=build_asset_catalog(resolved)
    plan=ScenePlanner(resolved,catalog).plan(0,0)
    # Known planar projection, deterministic source fixture; placements isolated from random tests.
    instances=tuple(replace(plan.instances[0],center=(64.+i*64,96.),angle_degrees=0,width_fraction=.25,object_attempt=i) for i in range(count))
    matrix=np.array([[1.,0,-32],[0,1,-32],[0,0,1]])
    plan=replace(plan,canvas_size=(192,192),camera_rect=(32.,32.,128.,128.),scene_to_output=matrix,
                 instances=instances,attempted_instances=count,intentional_negative=False,occluders=())
    # BackgroundSample has bounded provenance; renderer only needs its image.
    from types import SimpleNamespace
    bg=SimpleNamespace(image=np.full((192,192,3),140,np.uint8))
    return resolved,plan,bg


def layer(x1,y1,x2,y2,opacity=1):
    return SceneOccluder('debris',((x1,y1),(x2,y1),(x2,y2),(x1,y2)),(70,90,30),opacity)


def test_external_and_later_target_alpha_contributions():
    full=np.full((4,4),255,np.uint8)
    external=np.zeros_like(full); external[:,2:]=255
    a,b=visible_coverages([full,full],external)
    assert not a.any() and np.array_equal(b,255-external)
    with pytest.raises(ValueError,match='shape'):
        visible_coverages([full],np.zeros((3,3),np.uint8))


def test_partial_masks_boxes_and_threshold_boundary():
    resolved,plan,bg=setup_scene(floor=0)
    plan=replace(plan,occluders=(layer(64,0,192,192),))
    rendered=SceneRenderer(resolved).render(plan,bg)
    annotation=rendered.annotations[0]
    assert 0<annotation.visible_support_fraction<1
    full,visible=rendered.full_coverages[0],rendered.visible_coverages[0]
    assert (visible<=full).all() and not np.array_equal(full,visible)
    ys,xs=np.where(visible>resolved.family.annotation.alpha_threshold)
    assert annotation.bbox==(xs.min(),ys.min(),xs.max()+1,ys.max()+1)
    def with_floor(floor):
        scene=resolved.profile.scene.model_copy(update={'occlusion':SceneOcclusionConfig(min_visible_support=floor)})
        return resolved.model_copy(update={'profile':resolved.profile.model_copy(update={'scene':scene})})
    assert SceneRenderer(with_floor(annotation.visible_support_fraction)).render(plan,bg).annotations
    with pytest.raises(SceneRejected) as error:
        SceneRenderer(with_floor(annotation.visible_support_fraction+1e-6)).render(plan,bg)
    assert error.value.rejected_instances[0]['reason']=='visible_support_below_floor'


def test_best_effort_survivor_ids_and_require_count_after_occlusion():
    resolved,plan,bg=setup_scene(count=2)
    plan=replace(plan,occluders=(layer(0,0,96,192),))
    rendered=SceneRenderer(resolved).render(plan,bg)
    assert [a.instance_id for a in rendered.annotations]==['instance-001']
    assert len(rendered.full_coverages)==len(rendered.visible_coverages)==1
    assert rendered.rejected_instances[0]['reason']=='fully_occluded'
    sampling=resolved.profile.sampling.model_copy(update={'count_policy':'require-count'})
    required=resolved.model_copy(update={'profile':resolved.profile.model_copy(update={'sampling':sampling})})
    with pytest.raises(SceneRejected,match='require-count'):
        SceneRenderer(required).render(plan,bg)


def test_fully_hidden_positive_rejected_and_intentional_negative_preserved():
    resolved,plan,bg=setup_scene()
    plan=replace(plan,occluders=(layer(0,0,192,192),))
    with pytest.raises(SceneRejected,match='no accepted') as error:
        SceneRenderer(resolved).render(plan,bg)
    assert error.value.rejected_instances[0]['reason']=='fully_occluded'
    negative=replace(plan,instances=(),attempted_instances=0,intentional_negative=True)
    result=SceneRenderer(resolved).render(negative,bg)
    assert not result.annotations and not result.full_coverages
    assert result.scene_effects['occlusion']['applied']


def test_hidden_by_later_target_is_removed_without_new_occluders():
    resolved,plan,bg=setup_scene(count=2)
    plan=replace(plan,instances=(plan.instances[0],replace(plan.instances[0],object_attempt=1)))
    scene=resolved.profile.scene.model_copy(update={'occlusion':None})
    resolved=resolved.model_copy(update={'profile':resolved.profile.model_copy(update={'scene':scene})})
    result=SceneRenderer(resolved).render(plan,bg)
    assert [a.instance_id for a in result.annotations]==['instance-001']
    assert len(result.full_coverages)==1


def test_shared_projection_and_overlapping_occluders():
    image=np.full((80,80,3),150,np.uint8)
    occluders=(layer(10,10,30,30,.5),layer(10,10,30,30,.5))
    _,alpha=composite_occluders(image,occluders,np.array([[1.,0,7],[0,1,9],[0,0,1]]))
    assert alpha[25,25]==191 and alpha[5,5]==0
    assert alpha[19,17]>0 and alpha[9,7]==0


def test_independent_plan_streams_and_bounded_settings():
    resolved,_,_=setup_scene()
    catalog=build_asset_catalog(resolved)
    a=ScenePlanner(resolved,catalog).plan(0,0)
    b=ScenePlanner(resolved,catalog).plan(0,0)
    assert a.geometry_signature()==b.geometry_signature() and a.occluders==b.occluders
    scene=resolved.profile.scene.model_copy(update={'occlusion':None})
    plain=resolved.model_copy(update={'profile':resolved.profile.model_copy(update={'scene':scene})})
    c=ScenePlanner(plain,catalog).plan(0,0)
    assert [v.signature() for v in a.instances]==[v.signature() for v in c.instances]
    assert np.array_equal(a.scene_to_output,c.scene_to_output)
    assert a.geometry_signature()!=c.geometry_signature()
    for change in ({'count':[1,65]},{'opacity':[.5,1.1]},{'width_fraction':[.1,.5]}):
        with pytest.raises(ValueError): SceneOcclusionConfig(**change)


@pytest.mark.parametrize('family',['landing-pad','landing','manometro'])
def test_enabled_pipeline_serial_process_masks_and_exports(tmp_path,family):
    from helpers import write_derived_composer
    from dataset_generator_m1.generator import generate_pool, GenerationOptions
    from dataset_generator_m1.inspection import inspect_pool
    from dataset_generator_m1.exporter import export_pools, ExportOptions
    from dataset_generator_m1.execution_benchmark import _signature
    config=write_derived_composer(tmp_path,family,{'run':{'num_images':3},'output':{'image_size':[96,96]},
        'scene':{'lighting':{'probability':1},'occlusion':{'probability':1,'count':[12,12],'width_fraction':[.02,.04]}},
        'background_mixing':{'recipe_weights':{'direct':1.}},'execution':{'native_threads':1},'reporting':{'qa_samples':1}})
    resolved=load_profile(config)
    for name,workers in [('serial',1),('process',2)]:
        pool=tmp_path/name
        assert generate_pool(resolved,pool,GenerationOptions(display='quiet',workers=workers))['status']=='complete'
        assert inspect_pool(pool)['status']=='valid'
        rows=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines()]
        assert all(row['scene_effects']['occlusion']['applied'] for row in rows)
        assert all(0<a['visible_support_fraction']<=1 for row in rows for a in row['annotations'])
    assert _signature(tmp_path/'serial')==_signature(tmp_path/'process')
    for task in ['detection','segmentation']:
        export_pools([tmp_path/'serial'],tmp_path/task,ExportOptions(task=task,splits={'test':1.}))
        assert (tmp_path/task/'export.json').exists()
