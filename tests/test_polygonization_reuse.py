"""Exercise the actual worker result path; identical evidence needs one polygon projection."""
import os

import numpy as np
import pytest

from dataset_generator_m1 import generator
from dataset_generator_m1.annotation_evidence import decode_mask_evidence
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.config import load_profile
from helpers import write_derived_composer


@pytest.mark.parametrize('occlusion',[False,True])
def test_worker_reuses_projection_only_for_identical_full_visible_masks(tmp_path,monkeypatch,occlusion):
    config=write_derived_composer(tmp_path,'landing-pad',{'run':{'num_images':1},'output':{'image_size':[96,96]},
        'background_mixing':{'recipe_weights':{'direct':1.}},
        'scene':{'occlusion':{'probability':1,'count':[20,20],'width_fraction':[.04,.1]} if occlusion else None},
        'execution':{'native_threads':1},'reporting':{'qa_samples':0}})
    resolved=load_profile(config);calls=[];original=generator.polygonize_coverage
    def count(mask,**kwargs):
        calls.append(mask)
        return original(mask,**kwargs)
    monkeypatch.setattr(generator,'polygonize_coverage',count)
    result=generator._produce_slot(resolved,build_asset_catalog(resolved),0,0,os.getpid())
    assert result['accepted']
    masks=decode_mask_evidence(result['mask_archive'],result['record']['mask_evidence'])
    different=sum(not np.array_equal(m['full'],m['visible']) for m in masks.values())
    assert len(calls)==len(masks)+different
    if occlusion:assert different>0
    for item in result['record']['segmentation_quality']['instances']:
        for semantic in ['full','visible']:
            expected=original(masks[item['instance_id']][semantic],alpha_threshold=resolved.family.annotation.alpha_threshold)
            assert item['semantics'][semantic]['iou']==expected.iou
            assert item['semantics'][semantic]['area_error']==expected.area_error
            assert item['semantics'][semantic]['holes']==expected.holes
