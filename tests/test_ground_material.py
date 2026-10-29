import numpy as np
import pytest
from dataset_generator_m1.ground_material import GroundMapping, GroundMaterial, sample_spans
from dataset_generator_m1.blender_camera import ground_geometry, ground_uv
from dataset_generator_m1.blender_pilot import PilotConfig

def test_ground_mapping_stream_and_uv_tangent():
    assert sample_spans(10,3,(.5,1.5))==sample_spans(10,3,(.5,1.5))
    assert .5<=sample_spans(10,3,(.5,1.5))<=1.5
    assert sample_spans(10,3,(.5,1.5))!=sample_spans(10,4,(.5,1.5))
    a=np.array(ground_uv(0,0,2,90,(.2,.3)))
    b=np.array(ground_uv(2,0,2,90,(.2,.3)))
    assert np.allclose(b-a,[0,1])
    c=np.array(ground_uv(0,2,2,90,(.2,.3)))
    assert np.allclose(c-a,[-1,0])

def test_fixed_camera_ground_evidence():
    position=np.array([0.,0.,10.]);rotation=np.eye(3);K=np.array([[100,0,50],[0,100,50],[0,0,1.]])
    result=ground_geometry(position,rotation,K,(100,100),GroundMapping().model_dump(),2,1)
    assert result['central_view_width_m']==pytest.approx(10)
    assert result['tile_m']==pytest.approx(10)
    assert result['achieved_spans']==pytest.approx(1)
    assert result['coverage_guaranteed']

def test_modes_and_donor_validation():
    for name in ('coherent-blend','rgb-blend-stress','donor-mismatch-stress'):
        with pytest.raises(ValueError):GroundMaterial(mode=name)
        assert GroundMaterial(mode=name,donor_index=1).donor_index==1
    with pytest.raises(ValueError):GroundMaterial(mode='full',donor_index=1)
    with pytest.raises(ValueError,match='must differ'):GroundMaterial(mode='coherent-blend',primary_index=1,donor_index=1)
    with pytest.raises(ValueError):GroundMapping(ground_spans=(2,1))
    base={'reference_pool':'x','artwork':['a','b'],'grounds':[{'material_file':'x'}], 'environments':['a'],'treatments':[{'id':'base','ground_material':{'mode':'coherent-blend','donor_index':1}}]}
    with pytest.raises(ValueError,match='donor index'):PilotConfig.model_validate(base)

def test_prepare_opt_in_mapping_and_material_provenance(tmp_path,monkeypatch):
    import json
    from PIL import Image
    from dataset_generator_m1 import blender_pilot as pilot
    art=tmp_path/'art.png';Image.fromarray(np.full((12,12,4),255,np.uint8)).save(art);sha=pilot.digest_file(art)
    monkeypatch.setattr(pilot,'reference_scenes',lambda _:([{'objects':[{'center':[.5,.5],'fraction':.2,'angle':0,'source_sha256':sha}],'negative':False,'reference_image':'x'}],{'run_sha256':'x','samples_sha256':'x'}))
    grounds=[]
    for i in range(2):
        directory=tmp_path/f'g{i}';directory.mkdir();maps={}
        for role in ('color','roughness','normal'):
            path=directory/(role+'.jpg');path.write_bytes((str(i)+role).encode());maps[role]={'sha256':pilot.digest_file(path)}
        manifest=tmp_path/f'g{i}.json';manifest.write_text(json.dumps({'asset_id':directory.name,'license':'CC0-1.0','maps':maps}));grounds.append({'material_file':str(manifest)})
    hdr=tmp_path/'sky.hdr';hdr.write_bytes(b'sky');sky=tmp_path/'sky.json';sky.write_text(json.dumps({'license':'CC0-1.0','path':'sky.hdr','sha256':pilot.digest_file(hdr)}))
    config={'reference_pool':str(tmp_path),'artwork':[str(art),str(art)],'grounds':grounds,'environments':[str(sky)],'scenes':1,'ground_mapping':{},'treatments':[{'id':'base','ground_material':{'mode':'coherent-blend','donor_index':1}}]}
    source=tmp_path/'config.json';source.write_text(json.dumps(config));study=pilot.prepare(source,tmp_path/'study')
    job=study['jobs'][0]
    assert .5<=job['ground_spans']<=1.5
    assert job['treatment']['ground_material']['donor_index']==1
    assert study['config']['ground_mapping']['ground_spans']==[.5,1.5]
    assert 'src/dataset_generator_m1/ground_material.py' in study['contract']['harness_sources']
    config['scenes']=2;source.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='donor must differ'):pilot.prepare(source,tmp_path/'invalid')
    config['treatments'][0]['ground_material']['primary_index']=0
    source.write_text(json.dumps(config));whole=pilot.prepare(source,tmp_path/'whole')
    ordinary=[job for job in whole['jobs'] if job['case']=='ordinary' and job['quality']=='fast']
    assert [job['ground_index'] for job in ordinary]==[0,0]
    config['scenes']=1;config['scene_offset']=1;source.write_text(json.dumps(config))
    chunk=pilot.prepare(source,tmp_path/'chunk')['jobs'][0]
    assert chunk['ground_spans']==ordinary[1]['ground_spans']
    assert chunk['seed'] != ordinary[1]['seed']  # Legacy camera/scene seeds stay local.
    config['treatments'][0]['ground_material']['primary_index']=2
    with pytest.raises(ValueError,match='primary index'):pilot.PilotConfig.model_validate(config)

def test_role_aware_map_requirements_before_output(tmp_path,monkeypatch):
    import json
    from PIL import Image
    from dataset_generator_m1 import blender_pilot as pilot
    art=tmp_path/'art.png';Image.fromarray(np.full((8,8,4),255,np.uint8)).save(art);sha=pilot.digest_file(art)
    monkeypatch.setattr(pilot,'reference_scenes',lambda _:([{'objects':[{'center':[.5,.5],'fraction':.2,'angle':0,'source_sha256':sha}],'negative':False,'reference_image':'x'}],{'run_sha256':'x','samples_sha256':'x'}))
    grounds=[]
    for i,roles in enumerate((('color','roughness','normal'),('color',),('color',),('roughness','normal'))):
        directory=tmp_path/f'g{i}';directory.mkdir();maps={}
        for role in roles:
            path=directory/(role+'.jpg');path.write_bytes((str(i)+role).encode());maps[role]={'sha256':pilot.digest_file(path)}
        manifest=tmp_path/f'g{i}.json';manifest.write_text(json.dumps({'asset_id':directory.name,'license':'CC0-1.0','maps':maps}));grounds.append({'material_file':str(manifest)})
    hdr=tmp_path/'sky.hdr';hdr.write_bytes(b'sky');sky=tmp_path/'sky.json';sky.write_text(json.dumps({'license':'CC0-1.0','path':'sky.hdr','sha256':pilot.digest_file(hdr)}))
    variant={'mode':'rgb-blend-stress','primary_index':0,'donor_index':1}
    config={'reference_pool':str(tmp_path),'artwork':[str(art),str(art)],'grounds':grounds,'environments':[str(sky)],'scenes':2,'treatments':[{'id':'base','ground_material':variant}]}
    source=tmp_path/'config.json';source.write_text(json.dumps(config));pilot.prepare(source,tmp_path/'rgb')
    variant.update(mode='donor-mismatch-stress',primary_index=2,donor_index=3)
    source.write_text(json.dumps(config));pilot.prepare(source,tmp_path/'mismatch')
    variant.update(mode='coherent-blend',primary_index=0,donor_index=1)
    source.write_text(json.dumps(config));destination=tmp_path/'invalid'
    with pytest.raises(ValueError,match='donor index 1 missing maps'):pilot.prepare(source,destination)
    assert not destination.exists()
    variant.update(mode='full',primary_index=2,donor_index=None)
    source.write_text(json.dumps(config));destination=tmp_path/'invalid-primary'
    with pytest.raises(ValueError,match='primary index 2 missing maps'):pilot.prepare(source,destination)
    assert not destination.exists()
