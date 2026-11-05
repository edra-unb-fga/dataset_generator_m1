"""Render ordinary procedural preset scenes and archive recoverable evidence."""
import hashlib,json,os,runpy,signal,subprocess,tarfile,time,traceback
from pathlib import Path
c=Path('/content');root=c/'procedural-study';root.mkdir();start=time.monotonic();state='failed';error=None
telemetry=None
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
 telemetry=subprocess.Popen(['nvidia-smi','--query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total,power.draw','--format=csv','-l','10'],stdout=(root/'gpu-telemetry.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
 spec=json.loads((c/'spec.json').read_text())
 for name,key in [('input.tar.gz.run.py','bootstrap_sha256'),('generate_scene_presets.py','cli_sha256')]:
  if hashlib.sha256((c/name).read_bytes()).hexdigest()!=spec[key]:raise ValueError('Checksum mismatch: '+name)
 bootstrap=runpy.run_path(str(c/'input.tar.gz.run.py'));unpack=bootstrap['unpack_bundle'];write_config=bootstrap['write_bundle_config'];manifest=unpack(str(c/'input.tar.gz'),w,expected_sha256=spec['bundle_sha256']);src=w/'source';bproc=w/'blenderproc-venv/bin/blenderproc';blender=w/'blender'
 for i,cmd in enumerate([['uv','sync','--project',str(src),'--locked'],['uv','venv','--python',os.sys.executable,str(w/'blenderproc-venv')],['uv','pip','install','--python',str(w/'blenderproc-venv/bin/python'),'-r',str(src/'experiments/blenderproc/requirements.txt')]]):run(cmd,min(210,remaining(120)),root/f'bootstrap-{i}.log')
 py=src/'.venv/bin/python';policy=root/'policy.json';run([str(py),str(src/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(src/'experiments/blenderproc/execution/profiles.json'),'--settings',str(src/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(policy),'--gpu'],min(30,remaining(90)),root/'guards.log')
 cfg=json.loads((w/'config.json').read_text());cfg.update(input_bundle_identity=manifest['identity'],execution_policy=str(policy));config=w/'run-config.json';config.write_text(json.dumps(cfg,indent=2))
 # One bounded natural-mixture run. The config itself is sealed in the input bundle.
 count=spec['scenes']; seed=spec['seed']; offset=spec['scene_offset']
 if type(count) is not int or not 1 <= count <= 40: raise ValueError('scenes must be 1..40')
 if type(seed) is not int or seed < 0: raise ValueError('invalid seed')
 if type(offset) is not int or not 0 <= offset <= 100000: raise ValueError('invalid offset')
 label='natural';out=root/'results'/label;out.parent.mkdir(exist_ok=True)
 chunk={**cfg,'seed':seed,'scene_offset':offset,'scenes':count}
 chunk_config=write_config(w,label+'-config.json',chunk)
 run([str(py),str(src/'scripts/blenderproc_pilot.py'),'prepare','--config',str(chunk_config),'--output-dir',str(out)],min(150,remaining(100)),root/(label+'-prepare.log'))
 jobs=json.loads((out/'study.json').read_text())['jobs']
 if len(jobs)!=count:raise RuntimeError(f'{label}: expected {count} jobs, got {len(jobs)}')
 run([str(py),str(src/'scripts/blenderproc_pilot.py'),'render','--output-dir',str(out),'--blenderproc',str(bproc),'--blender-install-path',str(blender)],remaining(80),root/(label+'-render.log'))
 run([str(py),str(src/'scripts/blenderproc_pilot.py'),'report','--output-dir',str(out)],min(60,remaining(55)),root/(label+'-report.log'))
 run([str(py),str(src/'experiments/blenderproc/studies/coordinated-candidate/natural/verify.py'),str(out),str(count)],min(40,remaining(40)),root/'verification.log')
 state='complete'
except BaseException as exc:
 error=f'{type(exc).__name__}: {exc}';traceback.print_exc()
finally:
 if telemetry is not None:
  telemetry.terminate()
  try: telemetry.wait(timeout=5)
  except subprocess.TimeoutExpired: telemetry.kill();telemetry.wait()
 archive=c/'procedural-results.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
  for p in [root/'results',root/'policy.json',root/'policy.json.basis.json',w/'run-config.json',*root.glob('*.log'),*w.glob('*-config.json'),c/'spec.json']:
   if p.exists():tar.add(p,arcname=p.name if p.parent==c else str(p.relative_to(root)),filter=lambda x:None if '/wear/' in '/'+x.name+'/' else x)
 h=hashlib.sha256(archive.read_bytes()).hexdigest();(c/'procedural-results.json').write_text(json.dumps({'status':state,'error':error,'sha256':h,'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-start},indent=2))
