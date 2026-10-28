import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from dataset_generator_m1 import blender_pilot as pilot


def test_surface_controls_are_bounded_and_legacy_defaults_remain():
    treatment=pilot.Treatment(id='base')
    assert treatment.wear is None and treatment.pad_bump_strength is None
    assert treatment.ground_normal_strength is None and treatment.casters is None
    assert treatment.environment_index is None and treatment.lamps is None
    for data in ({'wear':{'unknown':1}}, {'pad_bump_distance_m':.1},
                 {'ground_normal_strength':3}, {'lamps':[{'color':[2,0,0]}]},
                 {'casters':{'count':13}}):
        with pytest.raises(ValueError):pilot.Treatment(id='base',**data)


def test_preparation_seals_wear_maps_and_variable_ground_selection(tmp_path,monkeypatch):
    art=tmp_path/'art.png';Image.fromarray(np.full((20,24,4),255,np.uint8)).save(art)
    art_hash=pilot.digest_file(art)
    monkeypatch.setattr(pilot,'reference_scenes',lambda _: ([{'objects':[{'center':[.5,.5],'fraction':.2,'angle':0,'source_sha256':art_hash}], 'negative':False,'reference_image':'none'}], {'run_sha256':'x','samples_sha256':'x'}))
    grounds=[]
    for index in range(4):
        directory=tmp_path/f'g{index}';directory.mkdir();(directory/'color.jpg').write_bytes(b'color')
        manifest=tmp_path/f'g{index}.json';manifest.write_text(json.dumps({'asset_id':directory.name,'license':'CC0-1.0','maps':{'color':{'sha256':pilot.digest_file(directory/'color.jpg')}}}))
        grounds.append({'material_file':str(manifest)})
    envs=[]
    for index in range(2):
        image=tmp_path/f'e{index}.hdr';image.write_bytes(b'hdr')
        manifest=tmp_path/f'e{index}.json';manifest.write_text(json.dumps({'license':'CC0-1.0','path':image.name,'sha256':pilot.digest_file(image)}));envs.append(str(manifest))
    config={'reference_pool':str(tmp_path),'artwork':[str(art),str(art)],'grounds':grounds,'environments':envs,'scenes':4,'treatments':[{'id':'wear','wear':{'fade':.1},'wear_seed':17,'casters':{'seed':7}}]}
    file=tmp_path/'config.json';file.write_text(json.dumps(config))
    study=pilot.prepare(file,tmp_path/'study')
    ordinary=[j for j in study['jobs'] if j['case']=='ordinary' and j['quality']=='fast']
    assert [j['ground_index'] for j in ordinary]==[0,1,2,3]
    assert [j['reference_scene_index'] for j in ordinary]==[0,0,0,0]
    assert all(j['wear_maps'][0]['seed']==17 for j in ordinary)
    assert all(j['casters'] and not j['casters'][0]['visible_camera'] for j in ordinary)
    entry=ordinary[0]['wear_maps'][0]['maps']['height']
    assert pilot.digest_file(entry['path'])==entry['sha256']
    assert pilot.load_study(tmp_path/'study')['identity']==study['identity']
    Path(entry['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        pilot.validate_inputs(study,Path(pilot.__file__).resolve().parents[2]/'experiments/blenderproc/render.py')


def test_scene_offset_resolves_and_wraps_reference_indices(tmp_path,monkeypatch):
    art=tmp_path/'art.png';Image.fromarray(np.full((12,12,4),255,np.uint8)).save(art)
    sha=pilot.digest_file(art)
    scenes=[{'objects':[{'center':[.1*(i+1),.5],'fraction':.2,'angle':0,'source_sha256':sha}],'negative':False,'reference_image':str(i)} for i in range(3)]
    monkeypatch.setattr(pilot,'reference_scenes',lambda _: (scenes,{'run_sha256':'x','samples_sha256':'x'}))
    ground=tmp_path/'ground';ground.mkdir();(ground/'color.jpg').write_bytes(b'color')
    g=tmp_path/'ground.json';g.write_text(json.dumps({'asset_id':'ground','license':'CC0-1.0','maps':{'color':{'sha256':pilot.digest_file(ground/'color.jpg')}}}))
    hdr=tmp_path/'sky.hdr';hdr.write_bytes(b'sky');e=tmp_path/'sky.json';e.write_text(json.dumps({'license':'CC0-1.0','path':'sky.hdr','sha256':pilot.digest_file(hdr)}))
    config={'reference_pool':str(tmp_path),'artwork':[str(art),str(art)],'grounds':[{'material_file':str(g)}],'environments':[str(e)],'scenes':3,'scene_offset':2,'treatments':[{'id':'base'}]}
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    study=pilot.prepare(path,tmp_path/'study')
    jobs=[j for j in study['jobs'] if j['case']=='ordinary' and j['quality']=='fast']
    assert [j['reference_scene_index'] for j in jobs]==[2,0,1]
    assert [j['scene']['reference_image'] for j in jobs]==['2','0','1']
    for name,selection,expected in [('omitted',None,['base']),('empty',[],[]),('selected',['second'],['second'])]:
        config['treatments']=[{'id':'base'},{'id':'second'}]
        if selection is None:config.pop('quality_treatments',None)
        else:config['quality_treatments']=selection
        path.write_text(json.dumps(config))
        selected=pilot.prepare(path,tmp_path/('study-'+name))
        quality=[job['treatment']['id'] for job in selected['jobs'] if job['case']=='ordinary' and job['quality']=='quality' and job['scene_index']==0]
        assert quality==expected
    config['quality_treatments']=['unknown']
    with pytest.raises(ValueError,match='Unknown quality treatment'):pilot.PilotConfig.model_validate(config)
    config['quality_treatments']=[]
    config['scene_offset']=-1
    with pytest.raises(ValueError):pilot.PilotConfig.model_validate(config)
