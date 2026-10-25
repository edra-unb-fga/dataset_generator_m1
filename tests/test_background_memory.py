"""Numerical/non-mutation and DAG ownership checks for bounded background workspaces."""
import weakref

import numpy as np
import pytest

from dataset_generator_m1 import backgrounds
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.models import BackgroundRecipe


@pytest.mark.parametrize('operation',['palette','blend','mask','displace','qa'])
@pytest.mark.parametrize('dtype',[np.float32,np.float64])
def test_background_operations_accept_readonly_inputs_without_mutation(operation,dtype):
    rng=np.random.default_rng(12)
    image=rng.uniform(.05,.95,(48,64,3)).astype(dtype)
    other=rng.uniform(.05,.95,(48,64,3)).astype(dtype)
    mask=rng.uniform(0,1,(48,64)).astype(dtype)
    values=[image,other,mask];snapshots=[v.copy() for v in values]
    for value in values:value.flags.writeable=False
    if operation=='palette': backgrounds._palette_transfer(image,other,.5)
    elif operation=='blend': backgrounds._multiband_blend(image,other,mask,2)
    elif operation=='mask': backgrounds._normalize_mask(mask,{'blur_fraction':.01},(64,48))
    elif operation=='displace': backgrounds._displace(image,mask,mask,.005,.01)
    else: backgrounds._qa(image)
    for value,snapshot in zip(values,snapshots):np.testing.assert_array_equal(value,snapshot)


def test_dead_background_intermediates_released_before_final_qa(monkeypatch):
    resolved=load_profile('examples/configs/landing-pad_minimal.yaml')
    catalog=build_asset_catalog(resolved)
    synthesizer=backgrounds.BackgroundSynthesizer(catalog,resolved.recipes)
    references={}
    execute=synthesizer._execute_node
    def observe(node,*args):
        value=execute(node,*args)
        if isinstance(value,np.ndarray):references[node.id]=weakref.ref(value)
        return value
    monkeypatch.setattr(synthesizer,'_execute_node',observe)
    qa=backgrounds._qa
    def bounded_qa(image):
        assert references['first_canvas']() is None
        assert references['second_canvas']() is None
        assert references['mask_canvas']() is None
        assert references['mask_luma']() is None
        assert references['mask']() is None
        return qa(image)
    monkeypatch.setattr(backgrounds,'_qa',bounded_qa)
    synthesizer.synthesize('mask_multiband',(96,64),np.random.default_rng(4))


def test_early_output_and_late_asset_parameter_references_remain_live():
    resolved=load_profile('examples/configs/landing-pad_minimal.yaml')
    recipe=BackgroundRecipe.model_validate({'nodes':[
        {'id':'source','op':'sample_asset'},
        {'id':'canvas','op':'resize_crop','inputs':{'image':'source'}},
        {'id':'later','op':'sample_asset','params':{'same_group_as':'source','distinct_from':['source']}},
        {'id':'unused','op':'resize_crop','inputs':{'image':'later'}}], 'output':'canvas'})
    recipes=resolved.recipes.model_copy(update={'recipes':{'early':recipe}})
    sample=backgrounds.BackgroundSynthesizer(build_asset_catalog(resolved),recipes).synthesize('early',(96,64),np.random.default_rng(4))
    assert sample.image.shape==(64,96,3)
    first,later=sample.source_assets
    assert first['group']==later['group'] and first['content_hash']!=later['content_hash']
    assert set(sample.node_timings_ns)=={'source','canvas','later','unused'}
    assert sample.sampled_parameters['later']['logical_path']==later['logical_path']
