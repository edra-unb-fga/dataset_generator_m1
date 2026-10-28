"""Compare paired 32- and 128-sample camera renders and create a review sheet."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',required=True,type=Path);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path);args=p.parse_args()
args.output_dir.mkdir(parents=True,exist_ok=True);records=[];tiles=[]
for cell in ('open-view','indoor-view','outdoor-view','motion-distortion'):
 for job in ('000-core-fast','001-core-fast'):
  original=args.baseline/cell/'scenes'/job;candidate=args.candidate/cell/'scenes'/job
  old=json.loads((original/'result.json').read_text());new=json.loads((candidate/'result.json').read_text())
  if old['renderer_settings']['samples']!=32 or new['renderer_settings']['samples']!=128:raise ValueError('Expected 32 and 128 sample settings')
  with np.load(original/'masks.npz',allow_pickle=False) as a,np.load(candidate/'masks.npz',allow_pickle=False) as b:
   same=sorted(a.files)==sorted(b.files) and all(np.array_equal(a[key],b[key]) for key in a.files)
  x=np.asarray(Image.open(original/'rgb.png').convert('RGB'),dtype=np.int16);y=np.asarray(Image.open(candidate/'rgb.png').convert('RGB'),dtype=np.int16)
  if x.shape!=y.shape:raise ValueError('Image shapes differ')
  records.append({'cell':cell,'job':job,'mask_equal':bool(same),'rgb_mean_abs_8bit':float(np.abs(x-y).mean()),'samples':128})
  if job=='001-core-fast':
   left=Image.fromarray(x.astype(np.uint8));right=Image.fromarray(y.astype(np.uint8));left.thumbnail((350,350));right.thumbnail((350,350));tiles.append((cell,left,right))
canvas=Image.new('RGB',(700,375*len(tiles)),'white');draw=ImageDraw.Draw(canvas)
for i,(cell,left,right) in enumerate(tiles):
 draw.text((5,i*375+2),cell+' : 32 samples (left), 128 samples (right)',fill='black');canvas.paste(left,(0,i*375+22));canvas.paste(right,(350,i*375+22))
canvas.save(args.output_dir/'sample-comparison.jpg',quality=90)
(args.output_dir/'sample-comparison.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'cases':len(records),'mask_matches':sum(r['mask_equal'] for r in records),'rgb_mean_abs_8bit_range':[min(r['rgb_mean_abs_8bit'] for r in records),max(r['rgb_mean_abs_8bit'] for r in records)]},indent=2))
