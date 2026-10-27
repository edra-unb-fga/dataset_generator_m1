import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from dataset_generator_m1.cell_handoff import import_archive, package, package_with_deadline
from dataset_generator_m1.ownership import CoordinatorLease


def test_camera_study_packages_completed_cells_at_locked_barrier(tmp_path, monkeypatch):
    script=Path('scripts/study_camera_environments.py')
    spec=importlib.util.spec_from_file_location('camera_study_handoff_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    matrix=tmp_path/'matrix.json'; matrix.write_text(json.dumps({'schema_version':1,'cells':[{'id':'one','jobs':['job']}] }))
    config=tmp_path/'config.json';config.write_text('{}')
    monkeypatch.setattr(module,'load_config',lambda _:SimpleNamespace(model_dump=lambda **kw:{'study_seconds':25,'treatments':[{}], 'camera_study':{}}))
    def prepare(conf,output):
        output.mkdir(parents=True)
        value={'identity':'identity'};(output/'study.json').write_text(json.dumps(value));return value
    monkeypatch.setattr(module,'prepare',prepare)
    def run(output,*args,**kwargs):
        result={'status':'complete','command_seconds':1.25}
        (output/'runs.json').write_text(json.dumps([result]));(output/'progress.json').write_text(json.dumps(result))
        return result
    monkeypatch.setattr(module,'run_study',run)
    monkeypatch.setattr(module,'completed_outputs',lambda *_:[])
    def check_barrier(root,cell,archive,*,lease,deadline):
        with pytest.raises(RuntimeError,match='active coordinator'):
            with CoordinatorLease(root):pass
        return package_with_deadline(root,cell,archive,lease=lease,deadline=deadline)
    monkeypatch.setattr(module,'package_with_deadline',check_barrier)
    root=tmp_path/'study'; dest=tmp_path/'archives'
    monkeypatch.setattr(sys,'argv',['driver','--config',str(config),'--matrix',str(matrix), '--output-dir',str(root),
        '--blenderproc','unused','--blender-install-path','unused','--total-seconds','100','--handoff-dir',str(dest)])
    module.main()
    budget=json.loads((root/'budget.json').read_text());summary=json.loads((root/'summary.json').read_text())
    assert budget['policy']['basis']=='elapsed_wall_time'
    assert budget['entries'][0]['charged_seconds']==1.25 and budget['entries'][0]['status']=='settled'
    assert summary['status']=='complete' and summary['elapsed_seconds']>=0
    assert import_archive(dest/'one.tar.gz',tmp_path/'import')['status']=='imported'
    assert import_archive(dest/'one.tar.gz',tmp_path/'import')['status']=='already-imported'


def test_camera_study_failed_cell_is_not_packaged(tmp_path, monkeypatch):
    script=Path('scripts/study_camera_environments.py');spec=importlib.util.spec_from_file_location('camera_study_handoff_failure',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    matrix=tmp_path/'matrix.json';matrix.write_text(json.dumps({'schema_version':1,'cells':[{'id':'one','jobs':['job']}]}))
    config=tmp_path/'config.json';config.write_text('{}')
    monkeypatch.setattr(module,'load_config',lambda _:SimpleNamespace(model_dump=lambda **kw:{'study_seconds':25,'treatments':[{}], 'camera_study':{}}))
    def prepare(conf,output):
        output.mkdir(parents=True);value={'identity':'identity'};(output/'study.json').write_text(json.dumps(value));return value
    monkeypatch.setattr(module,'prepare',prepare)
    def run(output,*args,**kwargs):
        value={'status':'budget-limited','command_seconds':1.0};(output/'runs.json').write_text(json.dumps([value]));(output/'progress.json').write_text(json.dumps(value));return value
    monkeypatch.setattr(module,'run_study',run);monkeypatch.setattr(module,'completed_outputs',lambda *_:[])
    root=tmp_path/'study';dest=tmp_path/'archives'
    monkeypatch.setattr(sys,'argv',['driver','--config',str(config),'--matrix',str(matrix),'--output-dir',str(root),'--blenderproc','unused','--blender-install-path','unused','--total-seconds','100','--handoff-dir',str(dest)])
    with pytest.raises(RuntimeError,match='did not complete'):module.main()
    assert not (dest/'one.tar.gz').exists()
    with pytest.raises(ValueError,match='not complete'):package(root,'one',tmp_path/'bad.tar.gz')
    assert json.loads((root/'budget.json').read_text())['entries'][0]['outcome']=='budget-limited'


def test_expired_handoff_stops_before_next_cell(tmp_path, monkeypatch):
    spec=importlib.util.spec_from_file_location('camera_study_expiry',Path('scripts/study_camera_environments.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    matrix=tmp_path/'matrix.json';matrix.write_text(json.dumps({'schema_version':1,'cells':[{'id':'one','jobs':['job']},{'id':'two','jobs':['job']}]}))
    config=tmp_path/'config.json';config.write_text('{}'); calls=[]
    monkeypatch.setattr(module,'load_config',lambda _:SimpleNamespace(model_dump=lambda **kw:{'study_seconds':25,'treatments':[{}], 'camera_study':{}}))
    def prepare(conf,output):
        output.mkdir(parents=True);value={'identity':'identity'};(output/'study.json').write_text(json.dumps(value));return value
    def run(output,*args,**kwargs):
        calls.append(output.name);value={'status':'complete','command_seconds':1.0}
        (output/'runs.json').write_text(json.dumps([value]));(output/'progress.json').write_text(json.dumps(value));return value
    def expired(*args,**kwargs):
        with pytest.raises(RuntimeError,match='active coordinator'):
            with CoordinatorLease(args[0]):pass
        raise TimeoutError('Packaging deadline expired')
    monkeypatch.setattr(module,'prepare',prepare);monkeypatch.setattr(module,'run_study',run)
    monkeypatch.setattr(module,'completed_outputs',lambda *_:[]);monkeypatch.setattr(module,'package_with_deadline',expired)
    root=tmp_path/'study';dest=tmp_path/'archives'
    monkeypatch.setattr(sys,'argv',['driver','--config',str(config),'--matrix',str(matrix),'--output-dir',str(root),'--blenderproc','unused','--blender-install-path','unused','--total-seconds','100','--handoff-dir',str(dest)])
    with pytest.raises(TimeoutError,match='deadline'):module.main()
    assert calls==['one'] and not (root/'cells'/'two').exists()
    assert json.loads((root/'summary.json').read_text())['status']=='failed'
