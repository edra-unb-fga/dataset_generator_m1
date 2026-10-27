import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from dataset_generator_m1 import blender_pilot as pilot
from dataset_generator_m1.asset_licenses import validate_asset_license
from dataset_generator_m1.blender_bundle import build_bundle


def declared(redistributable):
    return {'license':'custom-license', 'author':'Example Author', 'source_url':'https://example.org/asset',
            'license_url':'https://example.org/license', 'attribution':'Example Author / Example',
            'restrictions':'No raw redistribution' if not redistributable else 'Attribution required',
            'allow_local_render_and_dataset':True, 'allow_redistribution':redistributable}


def fixture(tmp_path, monkeypatch, ground_license, environment_license):
    art=tmp_path/'art.png';Image.fromarray(np.full((12,12,4),255,np.uint8)).save(art)
    sha=pilot.digest_file(art)
    scenes=[{'objects':[{'center':[.5,.5],'fraction':.2,'angle':0,'source_sha256':sha}],
             'negative':False,'reference_image':'ref'}]
    monkeypatch.setattr(pilot,'reference_scenes',lambda _: (scenes,{'run_sha256':'x','samples_sha256':'x'}))
    ground=tmp_path/'ground';ground.mkdir();(ground/'color.jpg').write_bytes(b'color')
    gm=tmp_path/'ground.json';gm.write_text(json.dumps({**ground_license,'asset_id':'ground','maps':{'color':{'sha256':pilot.digest_file(ground/'color.jpg')}}}))
    hdr=tmp_path/'sky.hdr';hdr.write_bytes(b'sky');env=tmp_path/'sky.json'
    env.write_text(json.dumps({**environment_license,'path':'sky.hdr','sha256':pilot.digest_file(hdr)}))
    pool=tmp_path/'pool';pool.mkdir();(pool/'qa').mkdir();(pool/'qa/index.html').write_text('<html></html>')
    for name in ('run.json','summary.json','rejections.jsonl','metrics.jsonl','control.json','control-events.jsonl'):(pool/name).write_text('{}')
    (pool/'samples.jsonl').write_text('')
    config={'reference_pool':str(pool),'artwork':[str(art),str(art)],'grounds':[{'material_file':str(gm)}],
            'environments':[str(env)],'scenes':1,'quality_treatments':[],'treatments':[{'id':'base'}]}
    path=tmp_path/'config.json';path.write_text(json.dumps(config));return path


@pytest.mark.parametrize('key',['license','author','source_url','license_url','attribution','restrictions','allow_local_render_and_dataset','allow_redistribution'])
def test_unknown_rights_are_rejected(key):
    record=declared(True);record.pop(key)
    with pytest.raises(ValueError):validate_asset_license(record)


def test_cc0_shorthand_and_noncc0_permissions():
    validate_asset_license({'license':'CC0-1.0'},redistribution=True)
    validate_asset_license(declared(False))
    with pytest.raises(ValueError,match='redistribution'):validate_asset_license(declared(False),redistribution=True)
    bad=declared(True);bad['allow_local_render_and_dataset']=False
    with pytest.raises(ValueError,match='dataset'):validate_asset_license(bad)
    for value in ('yes',1,None):
        bad=declared(True);bad['allow_redistribution']=value
        with pytest.raises(ValueError,match='boolean'):validate_asset_license(bad)


def test_prepare_retains_declarations_and_omits_legacy_camera_fields(tmp_path,monkeypatch):
    path=fixture(tmp_path,monkeypatch,declared(False),declared(True))
    study=pilot.prepare(path,tmp_path/'study')
    for config in (study['config'],study['contract']['config']):
        assert 'camera_study' not in config and 'environment_mix' not in config
    assert all('camera_pose' not in job for job in study['jobs'])
    assert study['contract']['assets'][0]['manifest']['attribution']=='Example Author / Example'
    assert 'src/dataset_generator_m1/asset_licenses.py' in study['contract']['harness_sources']
    assert pilot.load_study(tmp_path/'study')['identity']==study['identity']
    config=json.loads(path.read_text());config['camera_study']={};path.write_text(json.dumps(config))
    enabled=pilot.prepare(path,tmp_path/'camera-study')
    assert 'camera_study' in enabled['config'] and all('camera_pose' in j for j in enabled['jobs'])


@pytest.mark.parametrize('blocked', ['ground','environment'])
def test_bundle_rejects_nonredistributable_raw_assets(tmp_path,monkeypatch,blocked):
    ground=declared(blocked!='ground');env=declared(blocked!='environment')
    path=fixture(tmp_path,monkeypatch,ground,env)
    assert pilot.prepare(path,tmp_path/'study')['jobs']
    destination=tmp_path/'bundle.tar.gz'
    with pytest.raises(ValueError,match='redistribution'):
        build_bundle(path,destination)
    assert not destination.exists()


def test_bundle_preserves_redistributable_provenance(tmp_path,monkeypatch):
    path=fixture(tmp_path,monkeypatch,declared(True),{'license':'CC0-1.0'})
    result=build_bundle(path,tmp_path/'bundle.tar.gz')
    import tarfile
    with tarfile.open(result['archive']) as archive:
        assert {'source/scripts/handoff_study_cell.py', 'source/scripts/study_camera_environments.py'} <= set(archive.getnames())
        material=json.load(archive.extractfile('inputs/ground-0.json'))
    assert material['author']=='Example Author' and material['allow_redistribution'] is True
