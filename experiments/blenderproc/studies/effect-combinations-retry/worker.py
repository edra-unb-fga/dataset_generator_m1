import hashlib,json,os,runpy,signal,subprocess,tarfile,time,traceback
from pathlib import Path
from retry_config import write_run_config
content=Path('/content');spec=json.loads((content/'retry-spec.json').read_text())
root=content/'realism-retry';root.mkdir(exist_ok=False);start=time.monotonic();childfile=content/'retry-child.json'
env={**os.environ,'MPLBACKEND':'Agg','PYTHONDONTWRITEBYTECODE':'1'}
def status(step,**extra):
 p=content/'retry-progress.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps({'step':step,'elapsed_seconds':time.monotonic()-start,**extra}));os.replace(tmp,p)
def run(args,limit,log):
 with log.open('w') as out:
  child=subprocess.Popen(args,stdout=out,stderr=subprocess.STDOUT,env=env,start_new_session=True)
  childfile.write_text(json.dumps({'pid':child.pid,'command':args[0]}))
  try:
   code=child.wait(timeout=limit)
   if code:raise RuntimeError(f'{Path(args[0]).name} exited {code}')
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:pass
   try:os.killpg(child.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   child.wait()
   raise
  finally:childfile.unlink(missing_ok=True)
def remaining(reserve=0):
 value=spec['remote_seconds']-(time.monotonic()-start)-reserve
 if value<=0:raise TimeoutError('Remote wall-time budget exhausted')
 return value
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
state='failed';error=None
try:
 for file,key in [('retry-input.tar.gz','bundle_sha256'),('retry-input.tar.gz.run.py','bootstrap_sha256'),('retry-matrix.json','matrix_sha256'),('retry-driver.py','driver_sha256'),('retry_config.py','config_helper_sha256')]:
  if sha(content/file)!=spec[key]:raise ValueError('Checksum mismatch: '+file)
 status('unpacking');unpack=runpy.run_path(str(content/'retry-input.tar.gz.run.py'))['unpack_bundle'];workspace=root/'workspace'
 manifest=unpack(str(content/'retry-input.tar.gz'),workspace,expected_sha256=spec['bundle_sha256'])
 source=workspace/'source';bproc=workspace/'blenderproc-venv/bin/blenderproc';blender=workspace/'blender'
 for i,cmd in enumerate((['uv','sync','--project',str(source),'--locked'],['uv','venv','--python',os.sys.executable,str(workspace/'blenderproc-venv')],['uv','pip','install','--python',str(workspace/'blenderproc-venv/bin/python'),'-r',str(source/'experiments/blenderproc/requirements.txt')])):
  status('bootstrap-'+str(i));run(cmd,min(210,remaining(100)),root/f'bootstrap-{i}.log')
 python=source/'.venv/bin/python';policy=root/'adaptive-policy.json';status('guards')
 run([str(python),str(source/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(source/'experiments/blenderproc/execution/profiles.json'),'--settings',str(source/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(policy),'--gpu'],min(30,remaining(80)),root/'guards.log')
 cfg=json.loads((workspace/'config.json').read_text());cfg.update(input_bundle_identity=manifest['identity'],execution_policy=str(policy));cfg['grounds']=cfg['grounds'][:3];cfg['environments']=cfg['environments'][:1]
 run_config=write_run_config(workspace,cfg);status('study')
 budget=remaining(60)
 run([str(python),'/content/retry-driver.py','--config',str(run_config),'--matrix','/content/retry-matrix.json','--output-dir',str(root/'results'),'--blenderproc',str(bproc),'--blender-install-path',str(blender),'--total-seconds',str(budget-15),'--handoff-dir',str(root/'handoffs')],budget,root/'study.log')
 state='complete'
except BaseException as exc:
 error=f'{type(exc).__name__}: {exc}';traceback.print_exc()
finally:
 try:
  status('packaging',result=state,error=error)
  archive=content/'retry-results.tar.gz';temp=archive.with_suffix('.partial')
  def compact(info):
   return None if '/wear/' in '/'+info.name+'/' else info
  with tarfile.open(temp,'w:gz',compresslevel=1) as tar:
   for p in (root/'results',root/'handoffs',root/'adaptive-policy.json',root/'adaptive-policy.json.basis.json',workspace/'run-config.json',*root.glob('*.log')):
    if p.exists():tar.add(p,arcname=str(p.relative_to(root)),filter=compact)
   for p in (content/'retry-spec.json',content/'retry-matrix.json',content/'retry-driver.py',content/'retry_config.py'):
    tar.add(p,arcname='definition/'+p.name)
  os.replace(temp,archive)
  info={'status':state,'error':error,'sha256':sha(archive),'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-start,'wear_maps_omitted':True}
  (content/'retry-results.json').write_text(json.dumps(info,indent=2));status('finished',result=state,error=error)
 except BaseException as exc:status('packaging-failed',error=str(exc));raise
