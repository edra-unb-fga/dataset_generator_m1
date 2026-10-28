"""Pure annotation/config/export checks require no Blender installation."""
import json
from pathlib import Path
import numpy as np
import pytest
from dataset_generator_m1 import blender_runner
from PIL import Image

from dataset_generator_m1.blender_pilot import Treatment, PilotConfig, annotation_rows, mask_rle, export_coco, export_yolo, digest_file, digest
from dataset_generator_m1.evaluation_io import instance_mask, prepare_dataset


def test_mask_rle_roundtrip_boxes_and_visibility_floor():
    for seed in range(8):
        mask=np.random.default_rng(seed).random((13,17))>.6
        assert np.array_equal(mask,instance_mask(mask_rle(mask),17,13))
    full=np.zeros((2,20,30),bool);full[:,2:12,4:14]=True
    visible=full.copy();visible[0,:7]=False;visible[1]=False
    rows=annotation_rows(visible,full,1)
    assert len(rows['visible'])==1
    assert rows['visible'][0]['bbox']==[4,7,10,5]
    assert rows['visible'][0]['visible_support_fraction']==.5
    visible[0,:11]=False
    with pytest.raises(ValueError,match='floor'):annotation_rows(visible,full,1)
    visible[0,0,0]=True
    with pytest.raises(ValueError,match='exceeds'):annotation_rows(visible,full,1)


def test_pilot_rejects_unknown_nonfinite_or_unbounded_options():
    with pytest.raises(ValueError):Treatment(id='unsafe/path')
    with pytest.raises(ValueError):Treatment(id='base',roughness=float('nan'))
    with pytest.raises(ValueError):Treatment(id='base',distortion=(1,0,0,0,0))
    with pytest.raises(ValueError):Treatment(id='base',unknown=1)


def fake_study(root):
    scene=root/'scenes'/'base';scene.mkdir(parents=True)
    image=np.full((32,48,3),120,np.uint8);Image.fromarray(image).save(scene/'rgb.png')
    full=np.zeros((1,32,48),bool);full[:,8:24,12:36]=True
    np.savez_compressed(scene/'masks.npz',visible=full,full=full)
    job={'id':'base','scene':{'negative':False},'scene_index':0}
    runtime={key:{} for key in ('config','artwork','grounds','environments')}
    contract={'jobs_sha256':digest([job]),'runtime_sha256':digest(runtime)};identity=digest(contract)
    row={'identity':identity,'job':job,'status':'accepted',
         'files':{f:digest_file(scene/f) for f in ('rgb.png','masks.npz')}}
    (scene/'result.json').write_text(json.dumps(row))
    (root/'study.json').write_text(json.dumps({'identity':identity,'contract':contract,'jobs':[job],**runtime}))
    return scene


def test_coco_bridge_and_optional_yolo_preserve_complete_labels(tmp_path):
    scene=fake_study(tmp_path)
    summary=export_coco(tmp_path)
    assert summary['images']==summary['instances']==1
    assert summary['export_seconds']>0
    prepared=prepare_dataset(tmp_path/'evaluation-visible.json',tmp_path/'prepared')
    assert prepared['domain']=='synthetic' and prepared['annotation_semantics']=='visible'
    statuses=export_yolo(tmp_path)
    assert all(v['status']=='complete' for v in statuses.values())
    for task in ('detection','segmentation'):
        assert (tmp_path/f'yolo-{task}'/'labels/1.txt').read_text().startswith('0 ')
    (scene/'rgb.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):export_coco(tmp_path)


def test_conversion_failure_keeps_coco_and_complete_detection(tmp_path):
    scene=fake_study(tmp_path)
    # One-pixel targets have valid COCO/detection masks but no polygon.
    mask=np.zeros((1,32,48),bool);mask[0,10,10]=True
    np.savez_compressed(scene/'masks.npz',visible=mask,full=mask)
    row=json.loads((scene/'result.json').read_text());row['files']['masks.npz']=digest_file(scene/'masks.npz')
    (scene/'result.json').write_text(json.dumps(row))
    export_coco(tmp_path);statuses=export_yolo(tmp_path)
    assert statuses['detection']['status']=='complete'
    assert statuses['segmentation']['status']=='unavailable'
    assert not (tmp_path/'yolo-segmentation').exists()
    assert (tmp_path/'coco-visible.json').exists()


def test_job_plan_tampering_and_checkpoint_file_set_are_rejected(tmp_path):
    from dataset_generator_m1.blender_pilot import load_study
    scene=fake_study(tmp_path)
    value=json.loads((tmp_path/'study.json').read_text());value['jobs'][0]['id']='changed'
    (tmp_path/'study.json').write_text(json.dumps(value))
    with pytest.raises(ValueError,match='changed'):load_study(tmp_path)


def test_bridge_uses_complete_typed_composers_and_only_color_maps(tmp_path):
    from dataset_generator_m1.blender_pilot import bridge_composers
    from dataset_generator_m1.config import load_profile
    paths=bridge_composers(tmp_path/'assets',tmp_path/'artwork',tmp_path/'composers',workers=2)
    profiles=[load_profile(p) for p in paths]
    assert profiles[0].profile.output.image_format=='png'
    assert set(profiles[0].profile.background_synthesis.recipe_weights)=={'planar'}
    assert all(p.endswith('color.jpg') for p in profiles[0].profile.assets.backgrounds.paths)
    assert profiles[1].profile.scene.foreground_resampling=='premultiplied'
    assert profiles[1].profile.scene.lighting is not None


def test_declared_schema_matches_model():
    schema=json.loads(Path('experiments/blenderproc/pilot.schema.json').read_text())
    assert schema==PilotConfig.model_json_schema()


@pytest.mark.parametrize('key',['config','artwork','grounds','environments'])
def test_runtime_payload_is_sealed(tmp_path,key):
    from dataset_generator_m1.blender_pilot import load_study
    fake_study(tmp_path)
    value=json.loads((tmp_path/'study.json').read_text());value[key]={'changed':True}
    (tmp_path/'study.json').write_text(json.dumps(value))
    with pytest.raises(ValueError,match='changed'):load_study(tmp_path)


def test_exports_refuse_active_renderer(tmp_path):
    from dataset_generator_m1.ownership import CoordinatorLease
    from dataset_generator_m1.blender_pilot import export_study
    fake_study(tmp_path)
    with CoordinatorLease(tmp_path):
        for export in (export_coco,export_yolo,lambda root:export_study(root,yolo=True)):
            with pytest.raises(RuntimeError,match='active coordinator'):export(tmp_path)


def test_prepared_input_and_host_source_changes_rejected(tmp_path,monkeypatch):
    from dataset_generator_m1 import blender_pilot as pilot
    pool=tmp_path/'pool';pool.mkdir()
    for name in ('run.json','samples.jsonl','art.png','color.jpg','sky.hdr'):(pool/name).write_bytes(b'original')
    sha=pilot.digest_file(pool/'art.png')
    study={'contract':{'harness_source_sha256':pilot.digest_file(pilot.__file__),
        'renderer_script_sha256':sha,'assets':[{'kind':'environment','manifest':{'sha256':sha}}],
        'reference':{'run_sha256':sha,'samples_sha256':sha}},
        'artwork':[{'path':str(pool/'art.png'),'sha256':sha}],
        'grounds':[{'maps':{'color':str(pool/'color.jpg')},'provenance':{'maps':{'color':{'sha256':sha}}}}],
        'environments':[str(pool/'sky.hdr')],'config':{'reference_pool':str(pool)}}
    monkeypatch.setattr(pilot,'reference_scenes',lambda path:None)
    renderer=pool/'renderer.py';renderer.write_bytes(b'original')
    pilot.validate_inputs(study,renderer)
    for name in ('run.json','samples.jsonl','art.png','color.jpg','sky.hdr','renderer.py'):
        (pool/name).write_bytes(b'changed')
        with pytest.raises(ValueError,match='changed'):pilot.validate_inputs(study,renderer)
        (pool/name).write_bytes(b'original')
    study['contract']['harness_source_sha256']='changed'
    with pytest.raises(ValueError,match='changed'):pilot.validate_inputs(study,renderer)


def test_export_freezes_missing_prepared_jobs_before_launch(tmp_path,monkeypatch):
    from dataset_generator_m1 import blender_pilot as pilot
    scene=fake_study(tmp_path)
    study=json.loads((tmp_path/'study.json').read_text())
    study['jobs'].append({'id':'later','scene':{'negative':False},'scene_index':1})
    study['contract']['jobs_sha256']=digest(study['jobs']);study['identity']=digest(study['contract'])
    row=json.loads((scene/'result.json').read_text());row['identity']=study['identity']
    (scene/'result.json').write_text(json.dumps(row));(tmp_path/'study.json').write_text(json.dumps(study))
    export_coco(tmp_path)
    monkeypatch.setattr(pilot,'validate_inputs',lambda *args:None)
    monkeypatch.setattr(blender_runner.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('must not launch after freeze'))
    with pytest.raises(ValueError,match='frozen'):
        pilot.run_study(tmp_path,'unused','unused',job_ids=['later'])


def test_completed_study_returns_without_probing_or_launching(tmp_path,monkeypatch):
    from dataset_generator_m1 import blender_pilot as pilot
    fake_study(tmp_path)
    monkeypatch.setattr(pilot,'validate_inputs',lambda *args:None)
    monkeypatch.setattr(blender_runner.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('completed study must not launch'))
    value=json.loads((tmp_path/'study.json').read_text());value['config']['study_seconds']=1
    value['contract']['runtime_sha256']=digest({key:value[key] for key in ('config','artwork','grounds','environments')});value['identity']=digest(value['contract'])
    (tmp_path/'study.json').write_text(json.dumps(value))
    record=json.loads((tmp_path/'scenes/base/result.json').read_text());record['identity']=value['identity'];(tmp_path/'scenes/base/result.json').write_text(json.dumps(record))
    # Existing historical completed studies remain readable without rendering new scenes.
    result=pilot.run_study(tmp_path,'unused','unused',job_ids=['base'])
    assert result['status']=='complete' and result['already_complete']
