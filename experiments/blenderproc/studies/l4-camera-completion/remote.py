"""Run bounded L4 camera study and archive all recoverable evidence on exit."""
import hashlib,json,os,runpy,subprocess,tarfile,time,traceback
from pathlib import Path
c=Path('/content'); root=c/'camera-completion';root.mkdir();start=time.monotonic();state='failed';error=None
spec=json.loads((c/'completion-plan.json').read_text());env={**os.environ,'MPLBACKEND':'Agg','PYTHONDONTWRITEBYTECODE':'1'}
def run(cmd,timeout,log):
 with log.open('w') as f: return subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=timeout,check=True)
try:
 unpack=runpy.run_path(str(c/'development-input.tar.gz.run.py'))['unpack_bundle']
 for name in ('development','holdout'):
  workspace=root/name;manifest=unpack(str(c/(name+'-input.tar.gz')),workspace,expected_sha256=spec['bundles'][name]);cfg=json.loads((workspace/'config.json').read_text());cfg['input_bundle_identity']=manifest['identity'];(workspace/'run-config.json').write_text(json.dumps(cfg,indent=2))
 w=root/'development';source=w/'source';bproc=w/'blenderproc-venv/bin/blenderproc';blender=w/'blender'
 for idx,cmd in enumerate([['uv','sync','--project',str(source),'--locked'],['uv','venv','--python',os.sys.executable,str(w/'blenderproc-venv')],['uv','pip','install','--python',str(w/'blenderproc-venv/bin/python'),'-r',str(source/'experiments/blenderproc/requirements.txt')]]):run(cmd,240,root/f'bootstrap-{idx}.log')
 python=source/'.venv/bin/python';policy=root/'adaptive-policy.json'
 run([str(python),str(source/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(source/'experiments/blenderproc/execution/profiles.json'),'--settings',str(source/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(policy),'--gpu'],30,root/'guards.log')
 for name in ('development','holdout'):
  p=root/name/'run-config.json';cfg=json.loads(p.read_text());cfg['execution_policy']=str(policy);p.write_text(json.dumps(cfg,indent=2))
 for phase in spec['phases']:
  remaining=spec['total_seconds']-(time.monotonic()-start)
  if remaining<60:raise TimeoutError('Insufficient time for next phase')
  name=phase['name'];output=root/'results'/name;output.parent.mkdir(exist_ok=True)
  if phase['kind']=='camera':
   command=[str(python),str(source/'scripts/study_camera_environments.py'),'--config',str(root/phase['workspace']/'run-config.json'),'--matrix',str(c/phase['matrix']),'--output-dir',str(output),'--blenderproc',str(bproc),'--blender-install-path',str(blender),'--total-seconds',str(min(remaining-30,phase['seconds'])),'--handoff-dir',str(root/'handoffs'/name)]
  else:command=[str(python),str(c/'speed.py'),str(output),str(w),str(bproc),str(blender)]
  print('START_PHASE',name,flush=True)
  run(command,min(remaining-20,phase['seconds']+60),root/(name+'.log'))
  print('END_PHASE',name,flush=True)
 state='complete'
except BaseException as exc:
 error=f'{type(exc).__name__}: {exc}';print('REMOTE_ERROR',error,flush=True);traceback.print_exc()
finally:
 try:
  archive=c/'camera-results.tar.gz'
  with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
   for path in [root/'results',root/'handoffs',root/'adaptive-policy.json',root/'adaptive-policy.json.basis.json',*root.glob('*.log'),root/'development/run-config.json',root/'holdout/run-config.json']:
    if path.exists():tar.add(path,arcname=path.relative_to(root).as_posix())
   for path in [c/'completion-plan.json',c/'development-matrix.json',c/'holdout-matrix.json',c/'quality-matrix.json',c/'speed.py']:
    tar.add(path,arcname='definition/'+path.name)
  h=hashlib.sha256()
  with archive.open('rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
  result={'status':state,'error':error,'sha256':h.hexdigest(),'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-start}
  (c/'camera-results.json').write_text(json.dumps(result,indent=2));print('ARCHIVE_READY',json.dumps(result),flush=True)
 except BaseException as exc:
  (c/'camera-results.json').write_text(json.dumps({'status':'archive-failed','error':str(exc)}));raise
