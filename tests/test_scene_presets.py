import pytest
from dataset_generator_m1.scene_presets import catalog, load_preset, sample
from dataset_generator_m1.blender_pilot import EnvironmentGeometrySettings, Treatment

@pytest.mark.parametrize('name', ['open', 'outdoor', 'indoor'])
def test_presets_are_bounded_deterministic_and_explicit(name):
    preset=load_preset(name)
    args=(preset, 123, 7, Treatment(id='base').model_dump(mode='json'),
          EnvironmentGeometrySettings().model_dump(mode='json'), 2, 2)
    result=sample(*args)
    assert result == sample(*args)
    assert result['environment_geometry'] == name
    assert result['treatment']['casters']['count'] == 0
    assert all(c['shape'] in ('box','cylinder','sphere','overhead-slab','overhead-slats') and not c['visible_camera'] for c in result['casters'])
    assert result['ground_index'] in (0,1)
    assert result['treatment']['environment_index'] in (0,1)
    assert 0 <= result['environment_geometry_settings']['wall_color'][0] <= 1
    if name == 'indoor':
        assert result['treatment']['lamps']
        assert result['treatment']['environment_strength'] == 0

def test_invalid_preset_path_and_distribution():
    with pytest.raises(ValueError): load_preset('../open')
    preset=load_preset('open').model_dump()
    preset['caster_count']=(2,1)
    from dataset_generator_m1.scene_presets import Preset
    with pytest.raises(ValueError): Preset.model_validate(preset)

def test_independent_streams():
    p=load_preset('open'); t=Treatment(id='base').model_dump(mode='json'); settings=EnvironmentGeometrySettings().model_dump(mode='json')
    altered=p.model_copy(update={'caster_count':(0,0)})
    a=sample(p,4,2,t,settings,2,2); b=sample(altered,4,2,t,settings,2,2)
    assert a['treatment'] == b['treatment']
    assert a['ground_index'] == b['ground_index']
    assert a['environment_geometry_settings'] == b['environment_geometry_settings']


def test_weighted_ground_validation_and_sampled_controls():
    from dataset_generator_m1.scene_presets import Preset
    p=load_preset('open').model_dump(mode='json')
    p['ground_weights']=[{'index':1,'weight':1}]
    p['lighting']=[{'value':'sun','weight':1}]
    p['caster_count']=[1,1]
    p['caster_shapes']=[{'value':'overhead-slats','weight':1}]
    p=Preset.model_validate(p)
    args=(p, 44, 0, Treatment(id='base').model_dump(mode='json'), EnvironmentGeometrySettings().model_dump(mode='json'))
    with pytest.raises(ValueError): sample(*args,1,1)
    result=sample(*args,2,1)
    assert result['ground_index']==1
    assert result['treatment']['lamps'][0]['kind']=='SUN'
    assert result['casters'][0]['shape']=='overhead-slats'
    assert result['environment_geometry_settings']['ceiling_roughness'] is not None
    Treatment.model_validate(result['treatment'])

def test_custom_preset_file(tmp_path):
    path=tmp_path/'custom.json'
    path.write_text((catalog()/'open.json').read_text())
    assert load_preset(path=path).id=='open'

def test_prepare_ordinary_jobs_and_validate_every_resolved_setting(tmp_path, monkeypatch):
    import json
    import numpy as np
    from PIL import Image
    from dataset_generator_m1 import blender_pilot as pilot
    art=tmp_path/'art.png'; Image.fromarray(np.full((12,12,4),255,np.uint8)).save(art)
    sha=pilot.digest_file(art)
    monkeypatch.setattr(pilot,'reference_scenes',lambda _: ([{'objects':[{'center':[.5,.5],'fraction':.2,'angle':0,'source_sha256':sha}], 'negative':False,'reference_image':'x'}], {'run_sha256':'x','samples_sha256':'x'}))
    ground=tmp_path/'ground';ground.mkdir();(ground/'color.jpg').write_bytes(b'color')
    g=tmp_path/'ground.json';g.write_text(json.dumps({'asset_id':'ground','license':'CC0-1.0','maps':{'color':{'sha256':pilot.digest_file(ground/'color.jpg')}}}))
    hdr=tmp_path/'sky.hdr';hdr.write_bytes(b'sky');e=tmp_path/'sky.json';e.write_text(json.dumps({'license':'CC0-1.0','path':'sky.hdr','sha256':pilot.digest_file(hdr)}))
    config={'reference_pool':str(tmp_path),'artwork':[str(art),str(art)],'grounds':[{'material_file':str(g)}], 'environments':[str(e)],'scenes':8,'treatments':[{'id':'base'}], 'environment_geometry_settings':{'min_half_width_m':7,'wall_thickness_m':.2}, 'procedural':load_preset('indoor').model_dump(mode='json')}
    path=tmp_path/'config.json';path.write_text(json.dumps(config));study=pilot.prepare(path,tmp_path/'study')
    assert study['config']['environment_geometry_settings']['min_half_width_m']==7
    assert 'environment_mix' not in study['config']
    assert all(job['environment_geometry_settings']['min_half_width_m']==7 for job in study['jobs'])
    assert len(study['jobs']) == 8
    assert all(job['case']=='ordinary' and job['quality']=='fast' for job in study['jobs'])
    for job in study['jobs']:
        pilot.Treatment.model_validate(job['treatment'])
        pilot.EnvironmentGeometrySettings.model_validate(job['environment_geometry_settings'])
        assert job['environment_geometry_settings']['wall_ground_index'] is None
        for light in job['treatment']['lamps']:
            assert 0 < light['spot_size_rad'] <= np.pi and 0 <= light['spot_blend'] <= 1
        for caster in job['casters']:
            assert caster['location'][2] - caster['scale'][2]/2 >= 0
    config['scenes']=4;config['scene_offset']=4;config['camera_study']={'preset':'drone'}
    path.write_text(json.dumps(config));chunk=pilot.prepare(path,tmp_path/'chunk')
    config['scenes']=8;config['scene_offset']=0
    path.write_text(json.dumps(config));whole=pilot.prepare(path,tmp_path/'whole')
    for actual,expected in zip(chunk['jobs'],whole['jobs'][4:],strict=True):
        for key in ('seed','scene','treatment','ground_index','casters','camera_pose','environment_geometry_settings'):
            assert actual[key]==expected[key]
    legacy={**config};legacy.pop('procedural')
    with pytest.raises(ValueError,match='require environment_mix'):
        pilot.PilotConfig.model_validate(legacy)
    source=tmp_path/'source.json';source.write_text(json.dumps(legacy))
    assert pilot.load_config(source,procedural=load_preset('indoor')).environment_geometry_settings.min_half_width_m==7
    for updates in ({'treatments':[{'id':'a'},{'id':'b'}]}, {'quality_treatments':['base']}):
        with pytest.raises(ValueError,match='one template treatment'):
            pilot.PilotConfig.model_validate({**config,**updates})

def test_indoor_fixture_bounds_use_emitter_extent():
    # Import only the pure helpers; the renderer itself requires Blender's runtime.
    import ast
    source=(catalog().parent/'render.py').read_text()
    module=ast.parse(source)
    functions=[node for node in module.body if isinstance(node,ast.FunctionDef) and node.name in {'fit_indoor_lamp','indoor_caster_fits'}]
    namespace={};exec(compile(ast.Module(body=functions,type_ignores=[]),'render.py','exec'),namespace)
    fit=namespace['fit_indoor_lamp'];valid=namespace['indoor_caster_fits']
    room={'half_width_m':3,'ceiling_height_m':4}
    area=fit([8,0,5],'AREA',2,room,.2)
    assert area[0] < 2 and area[2] < 3
    point=fit([8,0,5],'POINT',1.5,room,.2)
    assert point[0] < 1.5 and point[2] < 2.5
    assert fit([0,0,2],'POINT',3,room,.2) is None
    assert valid([0,0,2],[1,1,1],room,.2)
    assert not valid([2.8,0,2],[1,1,1],room,.2)
    assert not valid([0,0,3.8],[1,1,1],room,.2)
    assert not valid([0,0,.1],[1,1,1],room,.2)
