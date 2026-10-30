"""Run the sealed material study with bounded time and recoverable archive."""
import hashlib,json,os,runpy,signal,subprocess,tarfile,time,traceback
from pathlib import Path
c=Path('/content');root=c/'ground-study';root.mkdir();w=root/'workspace';start=time.monotonic();state='failed';error=None;spec={};env={**os.environ,'MPLBACKEND':'Agg','PYTHONDONTWRITEBYTECODE':'1'}
def run(cmd,limit,log):
 with log.open('w') as f:
  proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,start_new_session=True)
  try:
   if proc.wait(timeout=limit):raise RuntimeError(f'{cmd[0]} exited {proc.returncode}')
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait();raise
def remaining(reserve=0):
 x=spec['total_seconds']-(time.monotonic()-start)-reserve
 if x<=0:raise TimeoutError('Study wall budget exhausted')
 return x
try:
 spec=json.loads((c/'spec.json').read_text())
 for n,k in [('input.tar.gz.run.py','bootstrap_sha256'),('matrix.json','matrix_sha256')]:
  if hashlib.sha256((c/n).read_bytes()).hexdigest()!=spec[k]:raise ValueError('Checksum mismatch '+n)
 unpack=runpy.run_path(str(c/'input.tar.gz.run.py'))['unpack_bundle'];manifest=unpack(str(c/'input.tar.gz'),w,expected_sha256=spec['bundle_sha256']);src=w/'source';bproc=w/'blenderproc-venv/bin/blenderproc';blender=w/'blender'
 for i,cmd in enumerate([['uv','sync','--project',str(src),'--locked'],['uv','venv','--python',os.sys.executable,str(w/'blenderproc-venv')],['uv','pip','install','--python',str(w/'blenderproc-venv/bin/python'),'-r',str(src/'experiments/blenderproc/requirements.txt')]]):run(cmd,min(210,remaining(120)),root/f'bootstrap-{i}.log')
 py=src/'.venv/bin/python';policy=root/'policy.json';run([str(py),str(src/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(src/'experiments/blenderproc/execution/profiles.json'),'--settings',str(src/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(policy),'--gpu'],min(30,remaining(90)),root/'guards.log')
 cfg=json.loads((w/'config.json').read_text());cfg.update(input_bundle_identity=manifest['identity'],execution_policy=str(policy));config=w/'run-config.json';config.write_text(json.dumps(cfg,indent=2))
 run([str(py),str(src/'experiments/blenderproc/studies/ground-material-study/driver.py'),'--config',str(config),'--matrix',str(c/'matrix.json'),'--output-dir',str(root/'results'),'--blenderproc',str(bproc),'--blender-install-path',str(blender),'--total-seconds',str(remaining(50))],remaining(45),root/'study.log');state='complete'
except BaseException as exc:error=f'{type(exc).__name__}: {exc}';traceback.print_exc()
finally:
 archive=c/'ground-results.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
  for p in [root/'results',root/'policy.json',root/'policy.json.basis.json',w/'run-config.json',*root.glob('*.log'),c/'spec.json',c/'matrix.json']:
   if p.exists():tar.add(p,arcname=p.name if p.parent==c else str(p.relative_to(root)),filter=lambda x:None if '/wear/' in '/'+x.name+'/' else x)
 h=hashlib.sha256(archive.read_bytes()).hexdigest();(c/'ground-results.json').write_text(json.dumps({'status':state,'error':error,'sha256':h,'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-start},indent=2))
