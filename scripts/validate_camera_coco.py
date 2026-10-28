"""Export retrieved camera cells and check canonical masks, boxes and evaluation input."""
import argparse,json,tempfile
from pathlib import Path
import numpy as np
from dataset_generator_m1.blender_pilot import export_study
from dataset_generator_m1.evaluation_io import instance_mask,prepare_dataset

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--validation-dir',type=Path,required=True);args=p.parse_args()
validation_file=args.validation_dir/'validation.json';data=json.loads(validation_file.read_text())
records=[];counts={'annotations':0,'pixels_exact':0,'boxes_exact':0};errors=[]
with tempfile.TemporaryDirectory(prefix='camera-evaluation-') as temporary:
 for phase in ('development','holdout','quality'):
  directory=args.results/phase/'cells'
  if not directory.exists():continue
  for cell in sorted(directory.iterdir()):
   if not cell.is_dir():continue
   try:
    result=export_study(cell)
    for mode in ('visible','full'):
     prepare_dataset(cell/f'evaluation-{mode}.json',Path(temporary)/phase/cell.name/mode)
     coco=json.loads((cell/f'coco-{mode}.json').read_text());images={x['id']:x for x in coco['images']}
     for annotation in coco['annotations']:
      image=images[annotation['image_id']];path=(cell/image['file_name']).parent/'masks.npz'
      with np.load(path,allow_pickle=False) as masks:expected=masks[mode][annotation['instance_id']].astype(bool)
      actual=instance_mask(annotation['segmentation'],image['width'],image['height']).astype(bool)
      ys,xs=np.where(expected);box=[int(xs.min()),int(ys.min()),int(xs.max()+1-xs.min()),int(ys.max()+1-ys.min())]
      equal=bool(np.array_equal(expected,actual));box_equal=box==annotation['bbox']
      counts['annotations']+=1;counts['pixels_exact']+=int(equal);counts['boxes_exact']+=int(box_equal)
      if not equal or not box_equal:errors.append(f'{phase}/{cell.name}/{mode}/{annotation["id"]}')
    records.append({'phase':phase,'cell':cell.name,'status':'complete',**result})
   except Exception as exc:
    records.append({'phase':phase,'cell':cell.name,'status':'failed','error':f'{type(exc).__name__}: {exc}'})
    errors.append(f'{phase}/{cell.name}: {type(exc).__name__}: {exc}')
data['annotation_exports']=records;data['annotation_roundtrip']={'counts':counts,'errors':errors}
validation_file.write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({'cells':len(records),'counts':counts,'errors':errors},indent=2))
if errors:raise SystemExit(1)
