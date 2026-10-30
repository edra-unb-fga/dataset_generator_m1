"""Execute one sealed study phase inside Colab; always package recoverable evidence."""
import hashlib, json, os, runpy, subprocess, tarfile, time, traceback
from pathlib import Path

content=Path('/content')
spec=json.loads((content/'realism-phase.json').read_text())
root=content/('realism-round-'+spec['phase']);root.mkdir()
started=time.monotonic();state='failed';error=None
env={**os.environ,'MPLBACKEND':'Agg','PYTHONDONTWRITEBYTECODE':'1'}

def run(args, timeout, logfile):
    with logfile.open('w') as out:
        subprocess.run(args,stdout=out,stderr=subprocess.STDOUT,env=env,timeout=timeout,check=True)

try:
    for name,expected in (('realism-matrix.json',spec['matrix_sha256']),('realism-input.tar.gz.run.py',spec['bootstrap_sha256'])):
        if hashlib.sha256((content/name).read_bytes()).hexdigest()!=expected:raise ValueError('Uploaded definition checksum mismatch: '+name)
    unpack=runpy.run_path(str(content/'realism-input.tar.gz.run.py'))['unpack_bundle']
    workspace=root/'workspace'
    manifest=unpack(str(content/'realism-input.tar.gz'),workspace,expected_sha256=spec['bundle_sha256'])
    source=workspace/'source';bproc=workspace/'blenderproc-venv/bin/blenderproc';blender=workspace/'blender'
    for i,cmd in enumerate((['uv','sync','--project',str(source),'--locked'],
        ['uv','venv','--python',os.sys.executable,str(workspace/'blenderproc-venv')],
        ['uv','pip','install','--python',str(workspace/'blenderproc-venv/bin/python'),'-r',str(source/'experiments/blenderproc/requirements.txt')])):
        remaining=spec['remote_seconds']-(time.monotonic()-started)
        if remaining<=60:raise TimeoutError('No time remains for setup')
        run(cmd,min(240,remaining-30),root/f'bootstrap-{i}.log')
    python=source/'.venv/bin/python';policy=root/'adaptive-policy.json'
    run([str(python),str(source/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(source/'experiments/blenderproc/execution/profiles.json'),
         '--settings',str(source/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(policy),'--gpu'],30,root/'guards.log')
    cfg=json.loads((workspace/'config.json').read_text());cfg['input_bundle_identity']=manifest['identity'];cfg['execution_policy']=str(policy)
    cfg['grounds']=cfg['grounds'][:3];cfg['environments']=cfg['environments'][:1]
    (workspace/'run-config.json').write_text(json.dumps(cfg,indent=2))
    remaining=spec['remote_seconds']-(time.monotonic()-started)
    if remaining<=90:raise TimeoutError('No time remains for study')
    run([str(python),str(source/'scripts/study_camera_environments.py'),'--config',str(workspace/'run-config.json'),
         '--matrix',str(content/'realism-matrix.json'),'--output-dir',str(root/'results'),
         '--blenderproc',str(bproc),'--blender-install-path',str(blender),
         '--total-seconds',str(remaining-45),'--handoff-dir',str(root/'handoffs')],remaining-15,root/'study.log')
    state='complete'
except BaseException as exc:
    error=f'{type(exc).__name__}: {exc}';traceback.print_exc()
finally:
    try:
        archive=content/'realism-results.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
            for path in [root/'results',root/'handoffs',root/'adaptive-policy.json',root/'adaptive-policy.json.basis.json',
                         root/'workspace/run-config.json',*root.glob('*.log')]:
                if path.exists():tar.add(path,arcname=path.relative_to(root).as_posix())
            for path in (content/'realism-phase.json',content/'realism-matrix.json'):
                tar.add(path,arcname='definition/'+path.name)
        digest=hashlib.sha256()
        with archive.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        (content/'realism-results.json').write_text(json.dumps({'status':state,'error':error,'sha256':digest.hexdigest(),
            'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-started},indent=2))
    except BaseException as exc:
        (content/'realism-results.json').write_text(json.dumps({'status':'archive-failed','error':str(exc)}));raise
