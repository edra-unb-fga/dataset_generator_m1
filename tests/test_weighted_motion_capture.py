import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from dataset_generator_m1.capture_effects import apply_weighted_motion, validate_weighted_motion
from dataset_generator_m1.filters import apply_pipeline_traced, validate_transform_specs
from dataset_generator_m1.models import TransformSpec
from dataset_generator_m1.blender_execution import Catalog


@pytest.mark.parametrize('params', [
    {'kernels': [2], 'weights': [1]}, {'kernels': [3, 3], 'weights': [1, 1]},
    {'kernels': [3], 'weights': [0]}, {'kernels': [3], 'weights': [float('nan')]},
    {'kernels': [3], 'weights': [1, 2]}, {'kernels': [3], 'weights': [1], 'extra': 1},
])
def test_invalid_motion_distributions(params):
    with pytest.raises(ValueError):
        validate_weighted_motion(params, 'final')


def test_weighted_motion_is_reproducible_and_preserves_alpha():
    pixels=np.zeros((64, 64, 4), dtype=np.uint8)
    pixels[10:50, 10:50, :3]=255
    pixels[12:48, 12:48, 3]=255
    spec=TransformSpec(id='motion',type='WeightedMotionBlur',probability=1,
                       params={'kernels':[3,7,15], 'weights':[4,2,1]})
    validate_transform_specs([spec], 'final')
    a, at=apply_pipeline_traced(pixels,[spec],123,'final',preserve_alpha=True)
    b, bt=apply_pipeline_traced(pixels,[spec],123,'final',preserve_alpha=True)
    assert np.array_equal(a,b) and np.array_equal(a[:,:,3], pixels[:,:,3])
    assert at[0].applied_params==bt[0].applied_params
    assert at[0].applied_params[0]['kernel'] in (3,7,15)
    with pytest.raises(ValueError):validate_transform_specs([spec],'foreground')


@pytest.mark.parametrize('family,prob,expected', [('pad',.7,[.4,.2,.1]),('gauge',.6,[.4,.15,.05])])
def test_profile_motion_frequencies(family,prob,expected):
    name='coherent-balanced-manometro' if family=='gauge' else 'coherent-balanced'
    p=Path('src/dataset_generator_m1/profiles/builtin/appearance')/name/'profile.yaml'
    effects=yaml.safe_load(p.read_text())['value']['final']
    motion=next(e for e in effects if e['type']=='WeightedMotionBlur')
    weights=motion['params']['weights']; total=sum(weights)
    assert motion['probability']==prob
    assert [prob*x/total for x in weights]==pytest.approx(expected)


@pytest.mark.parametrize('family,expected', [('pad',[.3,.4,.2,.1]),('gauge',[.4,.4,.15,.05])])
def test_sampled_activation_and_severity_distribution(monkeypatch,family,expected):
    import dataset_generator_m1.capture_effects as capture
    monkeypatch.setattr(capture.A,'Compose',lambda *a,**kw:lambda **inputs:{'image':inputs['image']})
    name='coherent-balanced-manometro' if family=='gauge' else 'coherent-balanced'
    p=Path('src/dataset_generator_m1/profiles/builtin/appearance')/name/'profile.yaml'
    effects=yaml.safe_load(p.read_text())['value']['final']
    spec=TransformSpec.model_validate(next(e for e in effects if e['type']=='WeightedMotionBlur'))
    counts={0:0,3:0,7:0,15:0}; image=np.zeros((8,8,3),dtype=np.uint8)
    for seed in range(5000):
        _,trace=apply_pipeline_traced(image,[spec],seed,'final')
        counts[trace[0].applied_params[0]['kernel'] if trace[0].applied else 0]+=1
    assert [counts[k]/5000 for k in (0,3,7,15)]==pytest.approx(expected,abs=.025)


def test_legacy_guard_serialization_does_not_add_action():
    path=Path('experiments/blenderproc/execution/profiles.json')
    catalog=json.loads(path.read_text());catalog['guards'].pop('swap_out_action')
    assert 'swap_out_action' not in Catalog.model_validate(catalog).model_dump(mode='json')['guards']


def test_external_family_selects_manometro_candidate(tmp_path):
    from rich.console import Console
    from dataset_generator_m1.guided_start import _advanced_editor
    family=tmp_path/'external.yaml'
    family.write_text('schema_version: 1\nsubject: family\nvalue: {family: manometro}\n')
    document=yaml.safe_load(Path('examples/configs/manometro_minimal.yaml').read_text())
    document['family']=str(family)
    responses=iter(['coherent','yes','done'])
    result=_advanced_editor(document,tmp_path/'composer.yaml',Console(file=open(tmp_path/'ui.txt','w')),lambda *a,**kw:next(responses))
    assert result['appearance']['preset']=='builtin:appearance/coherent-varied-manometro'


def test_postprocess_checks_and_preserves_masks(tmp_path,monkeypatch):
    sys.path.insert(0, str(Path('scripts').resolve()))
    import postprocess_blender_capture as capture
    source=tmp_path/'study'; scene=source/'scenes'/'sample';scene.mkdir(parents=True)
    from PIL import Image
    Image.fromarray(np.full((32,32,3),90,dtype=np.uint8)).save(scene/'rgb.png')
    (scene/'masks.npz').write_bytes(b'mask evidence')
    from dataset_generator_m1.blender_pilot import digest_file
    row={'status':'accepted','files':{'rgb.png':digest_file(scene/'rgb.png'),'masks.npz':digest_file(scene/'masks.npz')}}
    monkeypatch.setattr(capture,'load_study',lambda _: {'identity':'study-identity'})
    monkeypatch.setattr(capture,'completed_outputs',lambda *_: [({'id':'sample'},scene,row)])
    first=capture.postprocess(source,tmp_path/'one','builtin:appearance/coherent-balanced',42)
    second=capture.postprocess(source,tmp_path/'two','builtin:appearance/coherent-balanced',42)
    assert first['identity']==second['identity']
    assert first['images'][0]['image_sha256']==second['images'][0]['image_sha256']
    assert (tmp_path/'one/scenes/sample/masks.npz').read_bytes()==b'mask evidence'
    assert (scene/'masks.npz').read_bytes()==b'mask evidence'
    with pytest.raises(ValueError):capture.postprocess(source,source/'nested','builtin:appearance/coherent-balanced',42)
