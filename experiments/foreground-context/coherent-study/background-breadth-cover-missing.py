"""Force unsampled background paths as direct sources in a bounded 2D follow-up."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import psutil

ROOT=Path.cwd(); sys.path.insert(0,str(ROOT/'scripts'))
from dataset_generator_m1.blender_runner import monitor
from dataset_generator_m1.identities import digest
from dataset_generator_m1.models import GenerationProfile
from guarded_effect_combinations import Policy, resolve_guards
from study_surface_2d import atomic_json, run_pool

HERE=Path(__file__).resolve(); SOURCE=ROOT/'experiments/foreground-context/coherent-study/run.py'
spec=importlib.util.spec_from_file_location('coherent_background_study',SOURCE)
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)
POLICY=ROOT/'experiments/foreground-context/coherent-study/one-worker-policy.json'
base=ROOT/'outputs/experiments/background-breadth-20261106'
output=ROOT/'outputs/experiments/background-breadth-20261106-forced'
paths=sorted(p.relative_to(ROOT/'backgrounds').as_posix() for p in (ROOT/'backgrounds').rglob('*.jpg'))

def worker(missing):
 records=[]
 for index,name in enumerate(missing):
  seeds=20261206+index
  current=study.profiles(output,'landing-pad','coherent-balanced',1,seeds,640,baseline='coherent-varied')['candidate']
  payload=current.profile.model_dump(mode='json')
  payload['assets']['backgrounds']['asset_weights']={'root0/'+p:float(p==name) for p in paths}
  payload['background_synthesis']['recipe_weights']={'direct':1.0}
  profile=GenerationProfile.model_validate(payload)
  current=current.model_copy(update={'profile':profile,'contract_hash':digest({'base':current.contract_hash,'forced_background':payload}),
      'applied_overrides':{'forced_background':name,'seed':seeds}})
  pool=output/f'asset-{index:03d}'
  print('Running forced background',name,flush=True)
  summary,inspection,plan,prep,wall,signature,rows=run_pool(current,pool,output/'observations.jsonl',acknowledged_codes=study.ACKNOWLEDGED)
  used=rows[0]['background']['sources'][0]['logical_path'].removeprefix('root0/')
  if used!=name:raise RuntimeError(f'Expected {name}, got {used}')
  record={'family':'landing-pad','variant':'forced-direct','background':name,'pool':pool.name,
   'accepted':summary['accepted_samples'],'inspection':inspection['status'],'seed':seeds,'signature':signature,'seconds':wall,
   'profile':profile.model_dump(mode='json')}
  records.append(record);atomic_json(output/'records.json',records)
 atomic_json(output/'summary.json',{'status':'complete','records':len(records),'note':'Each source is explicitly forced as a direct recipe; this is not natural sampling.'})

def main():
 if '--worker' in sys.argv:
  worker(json.loads((output/'missing.json').read_text()));return
 seen=set()
 for f in base.glob('*-candidate/samples.jsonl'):
  for line in f.read_text().splitlines():
   r=json.loads(line)
   for source in r['background']['sources']:seen.add(source['logical_path'].removeprefix('root0/'))
 missing=sorted(set(paths)-seen)
 print('Naturally unsampled paths:',len(missing),missing,flush=True)
 if not missing:return
 output.mkdir(parents=True,exist_ok=False)
 (output/'missing.json').write_text(json.dumps(missing,indent=2)+'\n')
 shutil.copyfile(HERE,output/'driver-source.py');shutil.copyfile(POLICY,output/'policy.json')
 policy=Policy.model_validate_json(POLICY.read_bytes());memory=psutil.virtual_memory()
 guards=resolve_guards(policy.guards,memory.total,memory.available)
 atomic_json(output/'guard-basis.json',{'available_bytes':memory.available,'total_bytes':memory.total,'guards':guards})
 outcome=monitor([[sys.executable,str(HERE),'--worker']],output,'study',policy.guards.timeout_seconds,guards)
 atomic_json(output/'result.json',outcome)
 if outcome['status']!='complete':raise RuntimeError(f"Study ended {outcome['status']}: {outcome['reason']}")
 print('Forced follow-up complete',flush=True)

if __name__=='__main__':main()
