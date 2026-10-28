"""Validate retrieved render evidence and make contact sheets for visual review."""
import hashlib,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
root=Path(sys.argv[1]);dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=True)
report={'phases':{},'errors':[],'notes':['Masks represent sharp frame-zero geometric support, even when RGB includes blur.','No real-image or trained-model performance evaluation was performed.']}
for phase in ('development','holdout','quality'):
 folder=root/'results'/phase
 if not folder.exists():report['phases'][phase]={'status':'missing'};continue
 summary=json.loads((folder/'summary.json').read_text());records=[];tiles=[]
 for cell in summary.get('records',[]):
  name=cell['cell'];cellroot=folder/'cells'/name;rows=[]
  for row in cell.get('rows',[]):
   path=cellroot/'scenes'/row['job'];f=path/'result.json'
   if not f.exists():report['errors'].append(f'{phase}/{name}/{row["job"]}: result missing');continue
   item=json.loads(f.read_text());entry={'job':row['job'],'status':item['status'],'attempts':len(item.get('attempts',[])),'camera':item.get('camera_diagnostics'),'ground':item.get('ground_diagnostics'),'environment':item.get('environment_geometry_diagnostics')}
   if item['status']=='accepted':
    for fname,digest in item['files'].items():
     h=hashlib.sha256((path/fname).read_bytes()).hexdigest()
     if h!=digest:report['errors'].append(f'{phase}/{name}/{row["job"]}: {fname} checksum mismatch')
    img=Image.open(path/'rgb.png').convert('RGB')
    with np.load(path/'masks.npz',allow_pickle=False) as masks:
     v=masks['visible'].astype(bool);full=masks['full'].astype(bool)
     if v.shape!=full.shape or v.ndim!=3 or v.shape[1:]!=(img.height,img.width):report['errors'].append(f'{phase}/{name}/{row["job"]}: mask dimensions')
     if np.any(v&~full):report['errors'].append(f'{phase}/{name}/{row["job"]}: visible outside full support')
     entry['objects']=len(v);entry['visible_pixels']=[int(x.sum()) for x in v];entry['full_pixels']=[int(x.sum()) for x in full]
     overlay=np.array(img);outline=np.zeros((img.height,img.width),dtype=bool)
     for mask in v:
      inner=mask.copy();inner[1:-1,1:-1] &= mask[:-2,1:-1]&mask[2:,1:-1]&mask[1:-1,:-2]&mask[1:-1,2:];outline |= mask & ~inner
     overlay[outline]=[0,255,80]
    if len([x for x in tiles if x[0]==name])<3:tiles.append((name,row['job'],img.copy(),Image.fromarray(overlay)))
   rows.append(entry)
  out=cell.get('outcome',{});records.append({'cell':name,'status':out.get('status'),'reason':out.get('reason'),'seconds':out.get('command_seconds'),'workers':out.get('workers'),'rows':rows})
 if tiles:
  width=320; height=190; sheet=Image.new('RGB',(width*3,height*math.ceil(len(tiles)/3)), 'white');d=ImageDraw.Draw(sheet)
  for i,(name,job,img,overlay) in enumerate(tiles):
   x=(i%3)*width;y=(i//3)*height;d.text((x+5,y+3),f'{name} / {job}',fill='black');img.thumbnail((155,305));overlay.thumbnail((155,305));sheet.paste(img,(x+3,y+24));sheet.paste(overlay,(x+162,y+24))
  sheet.save(dest/f'{phase}-review.jpg',quality=88)
 report['phases'][phase]={'status':summary.get('status'),'error':summary.get('error'),'records':records,'comparisons':summary.get('comparisons',[])}
speed=root/'results/speed/summary.json'
report['speed']=json.loads(speed.read_text()) if speed.exists() else {'status':'missing'}
(dest/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'phases':{k:v['status'] for k,v in report['phases'].items()},'speed':report['speed'].get('status'),'errors':report['errors']},indent=2))
