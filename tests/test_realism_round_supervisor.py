import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

PATH=Path('experiments/blenderproc/studies/realism-round/supervisor.py').resolve()
spec=importlib.util.spec_from_file_location('realism_supervisor',PATH)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_matrix_has_separate_intents_and_serial_render_cells():
    root=PATH.parent
    dev=json.loads((root/'development-matrix.json').read_text())
    hold=json.loads((root/'reserved-matrix.json').read_text())
    for matrix,count in ((dev,20),(hold,12)):
        a,b=matrix['cells'][:2]
        assert len(a['jobs'])==len(set(a['jobs']))==count
        assert a['jobs']==b['jobs']
    assert dev['cells'][0]['config']['seed'] != hold['cells'][0]['config']['seed']
    budget=json.loads((root/'budget.json').read_text())
    assert len(budget['phases'])*budget['watchdog_seconds_per_phase']<=budget['max_combined_allocation_seconds']


def test_supervisor_retrieves_stops_freezes_and_limits_phases(tmp_path,monkeypatch):
    output=tmp_path/'out';bundle=tmp_path/'input.tar.gz';bundle.write_bytes(b'bundle')
    Path(str(bundle)+'.run.py').write_text('bootstrap')
    calls=[];metadata={'status':'complete','bytes':4,'sha256':module.hashlib.sha256(b'data').hexdigest()}
    def call(colab,*args,**kwargs):
        calls.append(args[0])
        if args[0]=='download':
            Path(args[-1]).write_text(json.dumps(metadata)) if args[-2].endswith('.json') else Path(args[-1]).write_bytes(b'data')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module,'call',call)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *args,**kwargs:None)
    def run(*args):
        monkeypatch.setattr(sys,'argv',['supervisor',*map(str,args)]);module.main()
    run('run','--phase','development','--output',output,'--bundle',bundle,'--session','dev')
    assert calls[-1]=='stop' and (output/'development/results.tar.gz').read_bytes()==b'data'
    with pytest.raises(FileNotFoundError):run('run','--phase','reserved','--output',output,'--bundle',bundle,'--session','hold')
    review=tmp_path/'review.md';review.write_text('Independent review of development')
    run('freeze','--output',output,'--review',review,'--bundle',bundle)
    run('run','--phase','reserved','--output',output,'--bundle',bundle,'--session','hold')
    ledger=json.loads((output/'budget-ledger.json').read_text())
    assert sum(e['reserved_seconds'] for e in ledger['entries'])==5400
    with pytest.raises(ValueError,match='already reserved'):
        run('run','--phase','development','--output',output,'--bundle',bundle,'--session','extra')


def test_supervisor_attempts_stop_on_execution_failure(tmp_path,monkeypatch):
    output=tmp_path/'out';bundle=tmp_path/'input.tar.gz';bundle.write_bytes(b'bundle');Path(str(bundle)+'.run.py').write_text('bootstrap')
    calls=[]
    def call(colab,*args,**kwargs):
        calls.append(args[0])
        if args[0] in ('exec','download'):raise RuntimeError('mock failure')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module,'call',call);monkeypatch.setattr(module.subprocess,'Popen',lambda *args,**kwargs:None)
    monkeypatch.setattr(sys,'argv',['supervisor','run','--phase','development','--output',str(output),'--bundle',str(bundle),'--session','fail'])
    with pytest.raises(SystemExit):module.main()
    assert calls[-1]=='stop'
    assert json.loads((output/'development/status.json').read_text())['stop_confirmed']


def test_postprocessing_recovery_verifies_each_sealed_accepted_output(tmp_path):
    import copy
    import io
    import tarfile
    failure='operands could not be broadcast together with shapes (640,640,3) (1280,1280,3) '
    matrix={'schema_version':1,'cells':[{'id':'baseline','jobs':['job-1']}]}
    matrix_bytes=json.dumps(matrix).encode();phase={'phase':'development','matrix_sha256':module.hashlib.sha256(matrix_bytes).hexdigest(),'bundle_sha256':'example'}
    runtime={key:{} for key in ('config','artwork','grounds','environments')}
    jobs=[{'id':'job-1'}]
    contract={'jobs_sha256':module.fingerprint(jobs),'runtime_sha256':module.fingerprint(runtime)}
    identity=module.fingerprint(contract);study={**runtime,'jobs':jobs,'contract':contract,'identity':identity}
    selection={'device':'GPU'};selection['identity']=module.fingerprint(selection)
    execution={'study_identity':identity,'selection':selection}
    files={'rgb.png':b'image','masks.npz':b'masks'}
    result={'identity':identity,'job':jobs[0],'status':'accepted','execution':{'selection_identity':selection['identity']},
            'files':{k:module.hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    records=[{'cell':'baseline','study_identity':identity,'outcome':{'status':'complete','selected_jobs':['job-1']},'rows':[{'job':'job-1','status':'accepted'}]}]
    entries={'definition/realism-phase.json':json.dumps(phase).encode(),'definition/realism-matrix.json':matrix_bytes,
             'results/summary.json':json.dumps({'status':'failed','error':failure,'records':records}).encode(),
             'study.log':('ValueError: '+failure).encode(),'results/cells/baseline/study.json':json.dumps(study).encode(),
             'results/cells/baseline/execution.json':json.dumps(execution).encode(),
             'results/cells/baseline/scenes/job-1/result.json':json.dumps(result).encode(),
             **{'results/cells/baseline/scenes/job-1/'+k:v for k,v in files.items()}}
    archive=tmp_path/'results.tar.gz'
    def pack():
        with tarfile.open(archive,'w:gz') as tar:
            for name,data in entries.items():
                member=tarfile.TarInfo(name);member.size=len(data);tar.addfile(member,io.BytesIO(data))
    pack();validation=module.validate_broadcast_failure(archive,matrix,phase)
    assert validation['original_status']=='failed' and validation['accepted_jobs_verified']==1
    entries['results/cells/baseline/scenes/job-1/rgb.png']=b'corrupted';pack()
    with pytest.raises(ValueError,match='checksum'):module.validate_broadcast_failure(archive,matrix,phase)
    entries['results/cells/baseline/scenes/job-1/rgb.png']=b'image'
    bad=copy.deepcopy(records);bad[0]['rows'][0]['status']='rejected'
    entries['results/summary.json']=json.dumps({'status':'failed','error':failure,'records':bad}).encode();pack()
    with pytest.raises(ValueError,match='declared accepted'):module.validate_broadcast_failure(archive,matrix,phase)
    entries['results/summary.json']=json.dumps({'status':'failed','error':'different error','records':records}).encode();pack()
    with pytest.raises(ValueError,match='known resolution'):module.validate_broadcast_failure(archive,matrix,phase)
