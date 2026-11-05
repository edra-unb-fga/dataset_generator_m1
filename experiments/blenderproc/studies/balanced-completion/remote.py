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
 py=src/'.venv/bin/python';policy=root/'policy.json'; fresh=root/'fresh-policy.json'
 run([str(py),str(src/'scripts/blenderproc_adaptive_guards.py'),'--policy',str(src/'experiments/blenderproc/execution/profiles.json'),'--settings',str(src/'experiments/blenderproc/execution/adaptive-guards.json'),'--output',str(fresh),'--gpu'],min(30,remaining(90)),root/'guards.log')
 if hashlib.sha256((c/'original-policy.json').read_bytes()).hexdigest()!=spec['policy_sha256']:raise ValueError('Original policy checksum mismatch')
 old=json.loads((c/'original-policy.json').read_text()); new=json.loads(fresh.read_text())
 for k in ('min_available_gib','min_gpu_free_mib'):
  if old['guards'][k]<new['guards'][k]:raise ValueError('Original guard weaker than current guard: '+k)
 for k in ('rss_limit_gib','max_swap_out_mib','probe_timeout_seconds'):
  if old['guards'][k]>new['guards'][k]:raise ValueError('Original guard weaker than current guard: '+k)
 policy.write_bytes((c/'original-policy.json').read_bytes())
 cfg=json.loads((w/'config.json').read_text());cfg.update(input_bundle_identity=manifest['identity'],execution_policy=str(policy));config=w/'run-config.json';config.write_text(json.dumps(cfg,indent=2))
 # Three bounded studies: 200 candidate scenes in contiguous chunks and 20 held-out seed scenes.
 for label, seed, offset, count in [('candidate-1',20261026,100,100),('heldout',20261117,0,20)]:
  out=root/'results'/label;out.parent.mkdir(exist_ok=True)
  chunk={**cfg,'seed':seed,'scene_offset':offset,'scenes':count}
  chunk_config=write_config(w,label+'-config.json',chunk)
  run([str(py),str(src/'scripts/blenderproc_pilot.py'),'prepare','--config',str(chunk_config),'--output-dir',str(out)],min(150,remaining(100)),root/(label+'-prepare.log'))
  jobs=json.loads((out/'study.json').read_text())['jobs']
  if len(jobs)!=count:raise RuntimeError(f'{label}: expected {count} jobs, got {len(jobs)}')
  if label=='candidate-1' and json.loads((out/'study.json').read_text())['identity']!=spec['candidate1_identity']:
   raise ValueError('Reprepared candidate study identity differs from original')
  # Verify the bundled derivatives for the unchanged first chunk.
  expected=w/'derivatives/wear-hashes.json'
  if label=='candidate-0' and expected.exists():
   actual={j['id']:[{role:entry['sha256'] for role,entry in item['maps'].items()} for item in j['wear_maps']] for j in jobs if 'wear_maps' in j}
   if actual!=json.loads(expected.read_text()):raise RuntimeError('Bundle wear derivatives differ')
  ids=[f'{i:03d}-base-fast' for i in range(69,100)] if label=='candidate-1' else [f'{i:03d}-base-fast' for i in range(20)]
  run([str(py),str(src/'scripts/blenderproc_pilot.py'),'render','--output-dir',str(out),'--blenderproc',str(bproc),'--blender-install-path',str(blender),'--jobs',*ids],remaining(80),root/(label+'-render.log'))
  run([str(py),str(src/'scripts/blenderproc_pilot.py'),'report','--output-dir',str(out)],min(60,remaining(55)),root/(label+'-report.log'))
  actual={p.name for p in (out/'scenes').iterdir() if (p/'result.json').exists()}
  if actual!=set(ids):raise ValueError(f'{label}: completed IDs differ from selection')
  for job_id in ids:
   result=json.loads((out/'scenes'/job_id/'result.json').read_text())
   if result.get('status')!='accepted':raise ValueError(f'{label}: {job_id} was not accepted')
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
  for p in [root/'results',root/'policy.json',root/'policy.json.basis.json',root/'fresh-policy.json',root/'fresh-policy.json.basis.json',w/'run-config.json',*root.glob('*.log'),*w.glob('*-config.json'),c/'spec.json']:
   if p.exists():tar.add(p,arcname=p.name if p.parent==c else str(p.relative_to(root)),filter=lambda x:None if '/wear/' in '/'+x.name+'/' else x)
 h=hashlib.sha256(archive.read_bytes()).hexdigest();(c/'procedural-results.json').write_text(json.dumps({'status':state,'error':error,'sha256':h,'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-start},indent=2))
