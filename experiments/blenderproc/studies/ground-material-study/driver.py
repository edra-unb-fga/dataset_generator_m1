"""Render a bounded paired material matrix with pre-render intent assertions."""
import argparse,copy,hashlib,json,math,time
import numpy as np
from pathlib import Path
from dataset_generator_m1.blender_pilot import load_config,prepare,run_study,atomic_json
p=argparse.ArgumentParser()
for x in ('config','matrix','output-dir','blenderproc','blender-install-path'):p.add_argument('--'+x,required=True)
p.add_argument('--total-seconds',type=float,required=True);p.add_argument('--validate-only',action='store_true');a=p.parse_args();started=time.monotonic();root=Path(a.output_dir);root.mkdir();base=load_config(a.config).model_dump(mode='json');matrix=json.loads(Path(a.matrix).read_text());records=[];mask_baselines={}
try:
 for cell in matrix['cells']:
  remaining=a.total_seconds-(time.monotonic()-started)
  if remaining<45:raise TimeoutError('Insufficient study budget for another cell')
  cfg=copy.deepcopy(base);cfg['grounds']=[base['grounds'][i] for i in cell['ground_indices']];cfg['scenes']=1;cfg['scene_offset']=cell.get('scene_offset',0);cfg['study_seconds']=min(remaining-20,180);cfg['quality_treatments']=[];cfg['treatments']=[cell['treatment']];cfg['ground_mapping']=cell.get('ground_mapping');cfg['environment_mix']={'open':1,'indoor':0,'outdoor':0} if cell['environment']=='open' else {'open':0,'indoor':1,'outdoor':0}
  config=root/(cell['id']+'.json');atomic_json(config,cfg);out=root/cell['id'];study=prepare(config,out);jobs=[j for j in study['jobs'] if j['case']=='ordinary'];assert len(jobs)==1;job=jobs[0];t=job['treatment'];assert t['lighting']==cell['treatment']['lighting'];assert job['environment_geometry']==cell['environment'];assert t.get('ground_material')==cell['treatment'].get('ground_material') or (t.get('ground_material') and all(t['ground_material'].get(k)==v for k,v in cell['treatment']['ground_material'].items()))
  if cell.get('ground_mapping'):
   lo,hi=cell['ground_mapping']['ground_spans'];assert lo<=job['ground_spans']<=hi
  if cell['environment']=='indoor':assert any(x['kind']=='AREA' for x in t['lamps'])
  if cell['environment']=='open':
   assert t['lighting']=='environment' and any(x['kind']=='SUN' and abs(x['angular_size_rad']-.00918)<1e-9 for x in t['lamps'])
  if a.validate_only:
   records.append({'cell':cell['id'],'job':job['id']});continue
  outcome=run_study(out,a.blenderproc,a.blender_install_path,job_ids=[job['id']]);assert outcome['status']=='complete',outcome
  result=json.loads((out/'scenes'/job['id']/'result.json').read_text());assert result['status']=='accepted';diag=result['ground_diagnostics'];
  if cell.get('ground_mapping'):
   assert diag is not None and diag['coverage_guaranteed'] and not diag['tile_clamped']
   lo,hi=cell['ground_mapping']['ground_spans'];assert lo==hi and math.isclose(diag['achieved_spans'],lo,rel_tol=1e-6,abs_tol=1e-6),diag
  maskfile=out/'scenes'/job['id']/'masks.npz'
  with np.load(maskfile,allow_pickle=False) as masks:
   signature={k:hashlib.sha256(masks[k].tobytes()).hexdigest() for k in sorted(masks.files)}
  offset=cell.get('scene_offset',0);baseline=mask_baselines.setdefault(offset,signature);assert signature==baseline,('mask mismatch',cell['id'],offset)
  records.append({'cell':cell,'job':job['id'],'identity':study['identity'],'outcome':outcome,'ground_diagnostics':diag,'mask_signature':signature,'environment_diagnostics':result['environment_geometry_diagnostics']});atomic_json(root/'summary.json',{'status':'running','records':records});print('CELL_COMPLETE',cell['id'],flush=True)
 atomic_json(root/'summary.json',{'status':'complete','records':records,'elapsed_seconds':time.monotonic()-started})
except BaseException as exc:
 atomic_json(root/'summary.json',{'status':'failed','error':f'{type(exc).__name__}: {exc}','records':records,'elapsed_seconds':time.monotonic()-started});raise
