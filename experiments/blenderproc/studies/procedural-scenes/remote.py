"""Render ordinary procedural preset scenes and archive recoverable evidence."""
import hashlib,json,os,runpy,signal,subprocess,tarfile,time,traceback
from pathlib import Path
c=Path('/content');root=c/'procedural-study';root.mkdir();start=time.monotonic();state='failed';error=None
spec={};w=root/'workspace'; env={**os.environ,'MPLBACKEND':'Agg','PYTHONDONTWRITEBYTECODE':'1'}
def run(cmd,limit,log):
 with log.open('w') as f:
  proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,start_new_session=True)
  try:
   if proc.wait(timeout=limit): raise RuntimeError(f'{cmd[0]} exited {proc.returncode}')
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);proc.wait();raise
def remaining(reserve=0):
 x=spec['total_seconds']-(time.monotonic()-start)-reserve
 if x<=0:raise TimeoutError('Study budget exhausted')
 return x
try:
 spec=json.loads((c/'spec.json').read_text())
 for name,key in [('input.tar.gz.run.py','bootstrap_sha256'),('generate_scene_presets.py','cli_sha256')]:
  if hashlib.sha256((c/name).read_bytes()).hexdigest()!=spec[key]:raise ValueError('Checksum mismatch: '+name)
 unpack=runpy.run_path(str(c/'input.tar.gz.run.py'))['unpack_bundle'];manifest=unpack(str(c/'input.tar.gz'),w,expected_sha256=spec['bundle_sha256']);src=w/'source';bproc=w/'blenderproc-venv/bin/blenderproc';blender=w/'blender'
 for i,cmd in enumerate([['uv','sync','--project',str(src),'--locked'],['uv','venv','--python',os.sys.executable,str(w/'blenderproc-venv')],['uv','pip','install','--python',str(w/'blenderproc-venv/bin/python'),'-r',str(src/'experiments/blenderproc/requirements.txt')]]):run(cmd,min(210,remaining(120)),root/f'bootstrap-{i}.log')
 py=src/'.venv/bin/python';policy=root/'policy.json';run([str(py),str(src/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(src/'experiments/blenderproc/execution/profiles.json'),'--settings',str(src/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(policy),'--gpu'],min(30,remaining(90)),root/'guards.log')
 cfg=json.loads((w/'config.json').read_text());cfg.update(input_bundle_identity=manifest['identity'],execution_policy=str(policy));config=w/'run-config.json';config.write_text(json.dumps(cfg,indent=2))
 # The copied CLI imports the bundled source, not the controller environment.
 cli=src/'scripts/generate_scene_presets.py';cli.write_bytes((c/'generate_scene_presets.py').read_bytes())
 for preset in ('open','outdoor','indoor'):
  out=root/'results'/preset;out.parent.mkdir(exist_ok=True)
  run([str(py),str(cli),'prepare','--config',str(config),'--preset',preset,'--output',str(out)],min(90,remaining(70)),root/(preset+'-prepare.log'))
  jobs=[j['id'] for j in json.loads((out/'study.json').read_text())['jobs'] if j['id'].endswith('-base-fast')]
  if len(jobs)!=4:raise RuntimeError(f'{preset}: expected four ordinary jobs, got {jobs}')
  run([str(py),str(src/'scripts/blenderproc_pilot.py'),'render','--output-dir',str(out),'--blenderproc',str(bproc),'--blender-install-path',str(blender),'--jobs',*jobs],remaining(50),root/(preset+'-render.log'))
 state='complete'
except BaseException as exc:
 error=f'{type(exc).__name__}: {exc}';traceback.print_exc()
finally:
 archive=c/'procedural-results.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
  for p in [root/'results',root/'policy.json',root/'policy.json.basis.json',w/'run-config.json',*root.glob('*.log'),c/'spec.json']:
   if p.exists():tar.add(p,arcname=p.name if p.parent==c else str(p.relative_to(root)),filter=lambda x:None if '/wear/' in '/'+x.name+'/' else x)
 h=hashlib.sha256(archive.read_bytes()).hexdigest();(c/'procedural-results.json').write_text(json.dumps({'status':state,'error':error,'sha256':h,'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-start},indent=2))
