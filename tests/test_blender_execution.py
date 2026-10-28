"""Saved execution policy selection and identity checks need no Blender installation."""
import copy
import json
from pathlib import Path

import pytest

from dataset_generator_m1.blender_execution import Catalog, fingerprint, load_catalog, load_execution, resolve_execution


def hardware(*,cpu=2,colab=True,gpu=True,oidn=True,memory=15360):
    return {'cpu_count':cpu,'environment':'colab' if colab else 'local',
            'devices':[{'id':'gpu-0','name':'Tesla T4','backend':'OPTIX','oidn_gpu':oidn,'memory_mib':memory}] if gpu else []}


def test_automatic_selection_is_capability_and_workload_bound():
    c=load_catalog()
    small=resolve_execution(c,hardware(),(640,640));large=resolve_execution(c,hardware(),(1280,1280))
    assert (small['profile'],small['settings']['workers'],small['settings']['threads'])==('colab-t4-small',2,1)
    assert (large['profile'],large['settings']['workers'],large['settings']['threads'])==('colab-t4',1,2)
    generic=resolve_execution(c,hardware(cpu=16,colab=False),(640,640))
    assert generic['profile']=='gpu-oidn' and generic['settings']['workers']==1
    assert resolve_execution(c,hardware(oidn=False),(640,640))['profile']=='cpu'
    assert resolve_execution(c,hardware(gpu=False,cpu=24,colab=False),(1280,1280))['settings']['threads']==6
    assert resolve_execution(c,hardware(cpu=1),(640,640))['settings']['workers']==1
    assert resolve_execution(c,hardware(memory=None),(640,640))['profile']=='gpu-oidn'


def test_overrides_explicit_profile_and_incompatible_gpu_are_not_silent():
    c=load_catalog()
    result=resolve_execution(c,hardware(),(640,640),profile='cpu',threads=3,workers=2)
    assert result['settings']['device']=='CPU' and result['overrides']=={'threads':3,'workers':2}
    assert result['settings']['threads']==3 and result['settings']['workers']==2
    with pytest.raises(ValueError,match='compatible'):resolve_execution(c,hardware(oidn=False),(640,640),profile='gpu-oidn')
    with pytest.raises(ValueError,match='compatible'):resolve_execution(c,hardware(),(640,640),profile='missing')
    with pytest.raises(ValueError):resolve_execution(c,hardware(),(640,640),threads=0)
    with pytest.raises(ValueError):resolve_execution(c,hardware(),(640,640),workers=0)


def test_saved_policy_values_are_applied_without_selector_changes(tmp_path):
    data=load_catalog().model_dump(mode='json')
    cpu=next(p for p in data['profiles'] if p['id']=='cpu');cpu['settings']['thread_cap']=3
    p=tmp_path/'profiles.json';p.write_text(json.dumps(data))
    assert resolve_execution(load_catalog(p),hardware(gpu=False,cpu=24),(640,640))['settings']['threads']==3
    p.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError,match='Duplicate'):load_catalog(p)


def test_strict_policy_schema_rejects_unknown_duplicate_and_unsafe_settings():
    original=load_catalog().model_dump(mode='json')
    mutations=[lambda x:x.update(unknown=True),lambda x:x['profiles'].append(x['profiles'][0]),
               lambda x:x['profiles'][0]['settings'].update(workers=0),
               lambda x:x['profiles'][0]['match'].update(gpu_name_pattern='['),
               lambda x:x['profiles'][0]['settings'].update(denoiser='OPTIX')]
    for change in mutations:
        data=copy.deepcopy(original);change(data)
        with pytest.raises(ValueError):Catalog.model_validate(data)
    assert json.loads(Path('experiments/blenderproc/execution/schema.json').read_text())==Catalog.model_json_schema()


def test_execution_record_cannot_drift_after_output(tmp_path):
    c=load_catalog().model_dump(mode='json');selection=resolve_execution(c,hardware(),(640,640))
    study={'identity':'study','execution_catalog':c,'config':{'resolution':[640,640]}}
    path=tmp_path/'execution.json';path.write_text(json.dumps({'study_identity':'study','selection':selection}))
    assert load_execution(tmp_path,study)['selection']==selection
    broken=copy.deepcopy(selection);broken['settings']['threads']=6
    path.write_text(json.dumps({'study_identity':'study','selection':broken}))
    with pytest.raises(ValueError,match='changed'):load_execution(tmp_path,study)
    broken['identity']=fingerprint({k:v for k,v in broken.items() if k!='identity'})
    path.write_text(json.dumps({'study_identity':'study','selection':broken}))
    with pytest.raises(ValueError,match='prepared policy'):load_execution(tmp_path,study)


def test_guarded_initializer_does_not_restart_an_unchanged_engine(monkeypatch):
    import importlib.util,sys
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('blender_runtime',Path('experiments/blenderproc/runtime.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Render:
        resolution_percentage=100
        use_persistent_data=True
        assignments=0
        @property
        def engine(self):return 'CYCLES'
        @engine.setter
        def engine(self,value):self.assignments+=1
    render=Render();scene=SimpleNamespace(render=render,cycles=SimpleNamespace(debug_bvh_type='STATIC_BVH',debug_use_spatial_splits=True))
    monkeypatch.setitem(sys.modules,'bpy',SimpleNamespace(context=SimpleNamespace(scene=scene)))
    module.guarded_render_init();module.guarded_render_init()
    assert render.assignments==0


def test_policy_digest_preserves_the_exact_prepared_payload():
    # Older sealed policy payloads can omit a later optional match field.
    value=load_catalog().model_dump(mode='json')
    for p in value['profiles']:p['match'].pop('min_cpu_count',None)
    selection=resolve_execution(value,hardware(),(640,640))
    assert selection['catalog_sha256']==fingerprint(value)


def test_explicit_eight_workers_is_allowed_but_nine_is_rejected():
    catalog=load_catalog()
    assert resolve_execution(catalog,hardware(cpu=12), (640,640), profile='gpu-guarded', workers=8, threads=1)['settings']['workers']==8
    with pytest.raises(ValueError):
        resolve_execution(catalog,hardware(cpu=12), (640,640), profile='gpu-guarded', workers=9, threads=1)
