"""Legacy materialized pyramid is an exact numerical oracle for streamed workspaces."""
import cv2
import numpy as np
import pytest

from dataset_generator_m1.backgrounds import _multiband_blend


def materialized(first,second,mask,levels):
    # Deliberately retain the old calculation as a differential numerical reference.
    maximum=max(1,int(np.floor(np.log2(max(2,min(first.shape[:2])))))-3)
    levels=max(1,min(levels,maximum))
    gp_first=[first.astype(np.float32)];gp_second=[second.astype(np.float32)];gp_mask=[mask.astype(np.float32)]
    for _ in range(levels):
        gp_first.append(cv2.pyrDown(gp_first[-1]));gp_second.append(cv2.pyrDown(gp_second[-1]));gp_mask.append(cv2.pyrDown(gp_mask[-1]))
    lp_first=[gp_first[-1]];lp_second=[gp_second[-1]]
    for index in range(levels,0,-1):
        size=(gp_first[index-1].shape[1],gp_first[index-1].shape[0])
        lp_first.append(gp_first[index-1]-cv2.pyrUp(gp_first[index],dstsize=size))
        lp_second.append(gp_second[index-1]-cv2.pyrUp(gp_second[index],dstsize=size))
    blended=[]
    for a,b,m in zip(lp_first,lp_second,reversed(gp_mask)):
        weight=m[:,:,None];blended.append(a*weight+b*(1.-weight))
    result=blended[0]
    for level in blended[1:]:result=cv2.pyrUp(result,dstsize=(level.shape[1],level.shape[0]))+level
    return np.clip(result,0.,1.)


@pytest.mark.parametrize('shape',[(9,13),(32,48),(65,71),(128,96)])
@pytest.mark.parametrize('levels',[1,3,20])
@pytest.mark.parametrize('dtype',[np.float32,np.float64])
def test_streamed_multiband_matches_materialized_float_output_exactly(shape,levels,dtype):
    rng=np.random.default_rng(199)
    first=rng.random((*shape,3)).astype(dtype);second=rng.random((*shape,3)).astype(dtype);mask=rng.random(shape).astype(dtype)
    for value in (first,second,mask):value.flags.writeable=False
    expected=materialized(first,second,mask,levels)
    actual=_multiband_blend(first,second,mask,levels)
    np.testing.assert_array_equal(actual,expected)
