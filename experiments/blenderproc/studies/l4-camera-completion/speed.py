"""Paired same-host view-relative vs fixed-ground performance check."""
import copy,json,sys,time
from pathlib import Path
from dataset_generator_m1.blender_pilot import prepare,run_study,completed_outputs,load_config
root=Path(sys.argv[1]);root.mkdir();workspace=Path(sys.argv[2]);bp=sys.argv[3];blender=sys.argv[4]
base=load_config(workspace/'run-config.json').model_dump(mode='json');base.update(scenes=8,quality_treatments=[],study_seconds=300)
records=[];begin=time.monotonic()
try:
 for index,mode in enumerate(['fixed-physical','view-relative','view-relative','fixed-physical','fixed-physical','view-relative']):
  cfg=copy.deepcopy(base);cfg['camera_study']['material_mode']=mode
  conf=root/f'{index}.json';conf.write_text(json.dumps(cfg,indent=2));cell=root/f'cell-{index}';study=prepare(conf,cell)
  warm=run_study(cell,bp,blender,job_ids=['000-core-fast','001-core-fast'])
  if warm['status']!='complete':raise RuntimeError(f'warmup {index}: {warm}')
  ids=[f'{i:03}-core-fast' for i in range(2,8)];out=run_study(cell,bp,blender,job_ids=ids)
  rows=[r for j,p,r in completed_outputs(cell,study) if j['id'] in ids]
  accepted=sum(r['status']=='accepted' for r in rows)
  records.append({'index':index,'mode':mode,'warmup':warm,'outcome':out,'accepted':accepted,'images_per_second':accepted/out['command_seconds'] if out.get('command_seconds') else None})
  (root/'summary.json').write_text(json.dumps({'status':'running','records':records},indent=2))
  if out['status']!='complete' or accepted!=len(ids):raise RuntimeError(f'cell {index} incomplete')
 (root/'summary.json').write_text(json.dumps({'status':'complete','records':records,'elapsed_seconds':time.monotonic()-begin},indent=2))
except BaseException as e:
 (root/'summary.json').write_text(json.dumps({'status':'failed','error':str(e),'records':records},indent=2));raise
