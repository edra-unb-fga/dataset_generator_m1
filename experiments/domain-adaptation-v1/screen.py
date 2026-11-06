"""Guarded matched RGB-only domain/capture screen on verified retained scenes."""
import argparse, hashlib, json, os, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('ALBUMENTATIONS_NO_TELEMETRY','1')
os.environ.setdefault('NO_ALBUMENTATIONS_UPDATE','1')
import albumentations as A
import cv2, numpy as np, psutil
from PIL import Image
from dataset_generator_m1.blender_runner import monitor
from guarded_effect_combinations import Policy,resolve_guards
from study_surface_2d import atomic_json
cv2.setNumThreads(1)
REFS=['backgrounds/concrete_ground/Concrete048.jpg','backgrounds/gravel/Gravel032.jpg','backgrounds/wood/Wood058.jpg']
FAMS=('landing-pad','landing','manometro')
VARIANTS={'fda':[.01,.06,.18], 'histogram':[.15,.55,1.0], 'color':[.1,.35,.7], 'motion':[3,7,15], 'defocus':[1,3,7], 'noise':[.01,.05,.12], 'compression':[90,60,30], 'downscale':[.8,.5,.25]}

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def seed(*items):return int.from_bytes(hashlib.sha256(':'.join(map(str,items)).encode()).digest()[:4],'big')
def load_rgb(p):return np.asarray(Image.open(p).convert('RGB'))
def build_transform(name, value):
 if name=='fda':return A.FDA(beta_limit=(value,value),p=1)
 if name=='histogram':return A.HistogramMatching(blend_ratio=(value,value),p=1)
 if name=='color':return A.ColorJitter(brightness=(1-value,1+value),contrast=(1-value,1+value),saturation=(1-value,1+value),hue=(-min(.4,value*.4),min(.4,value*.4)),p=1)
 if name=='motion':return A.MotionBlur(blur_limit=(value,value),allow_shifted=False,p=1)
 if name=='defocus':return A.Defocus(radius=(value,value),p=1)
 if name=='noise':return A.GaussNoise(std_range=(value,value),mean_range=(0,0),per_channel=False,p=1)
 if name=='compression':return A.ImageCompression(quality_range=(value,value),compression_type='jpeg',p=1)
 if name=='downscale':return A.Downscale(scale_range=(value,value),interpolation_pair={'downscale':cv2.INTER_AREA,'upscale':cv2.INTER_LINEAR},p=1)
 raise ValueError(name)
def apply(rgb,name,value,local_seed,ref):
 t=build_transform(name,value); args={'image':rgb}
 if name=='fda':args['fda_metadata']=[ref]
 if name=='histogram':args['hm_metadata']=[ref]
 return A.Compose([t],seed=local_seed,strict=True)(**args)['image']
def sources():
 root=ROOT/'outputs/experiments/camera-capture-paired-20261105'; out=[]
 for family in FAMS:
  pool=root/(family+'-clean-capture')
  for line in (pool/'samples.jsonl').read_text().splitlines()[:4]:
   s=json.loads(line);path=pool/s['image_path'];out.append({'engine':'2D','family':family,'slot':s['slot'],'path':str(path),'sha256':digest(path),'annotations':s['annotations'],'background_hashes':[x['content_hash'] for x in s['background']['sources']],'source_sample_id':s['sample_id'],'source_signature':s['geometry_signature']})
 manifest=ROOT/'outputs/experiments/lighting-natural-balanced-reviewed-20261105/gallery/manifest.json';gallery=manifest.parent
 for index in [0,7,10,15]:
  s=json.loads(manifest.read_text())['images'][index];path=gallery/s['path']; out.append({'engine':'3D post-render','family':'landing-pad','slot':index,'path':str(path),'sha256':digest(path),'annotations':[],'background_hashes':[],'source_sample_id':s['label'],'source_3d_identity':s['metadata']['identity'],'source_3d_files':s['metadata'].get('files',{})})
 return out
def worker(out):
 refs=[]
 for item in REFS:
  p=ROOT/item; refs.append({'id':item,'sha256':digest(p),'image':load_rgb(p)})
 gallery=out/'gallery'; (gallery/'images').mkdir(parents=True); rows=[]; allsrc=sources()
 for source in allsrc:
  rgb=load_rgb(Path(source['path'])); refs_ok=[r for r in refs if r['sha256'] not in source['background_hashes']]
  if not refs_ok:raise ValueError('No non-identical development reference')
  ref=refs_ok[seed(source['engine'],source['family'],source['slot'])%len(refs_ok)]
  variants=[('clean','control',None)] + [(n,l,v) for n,values in VARIANTS.items() for l,v in zip(('mild','strong','extreme'),values)]
  variants += [('mix',str(i),i) for i in range(4)]
  for name,level,value in variants:
   k=seed(source['engine'],source['family'],source['slot'],name,level); steps=[]; image=rgb.copy()
   if name=='mix':
    rng=np.random.default_rng(k); z=float(rng.random()); limits=(.40,.80,.95,1.) if source['family']=='manometro' else (.30,.70,.90,1.)
    ksize=0 if z<limits[0] else 3 if z<limits[1] else 7 if z<limits[2] else 15
    if ksize: steps.append(('motion',ksize))
    if rng.random()<.5:steps.append(('color',.1 if value<2 else .35))
    if rng.random()<.4:steps.append(('noise',.01 if value<2 else .05))
    if rng.random()<.4:steps.append(('compression',90 if value<2 else 60))
   elif name!='clean': steps=[(name,value)]
   for i,(op,val) in enumerate(steps):image=apply(image,op,val,seed(k,i,op),ref['image'])
   if image.shape!=rgb.shape:raise ValueError('Unexpected shape change')
   rel=f"images/{source['engine'].replace(' ','-')}-{source['family']}-{source['slot']:03}-{name}-{level}.png";p=gallery/rel;Image.fromarray(image).save(p)
   meta={k:v for k,v in source.items() if k not in ('path','annotations')};meta.update({'image_sha256':digest(p),'treatment':name,'severity':level,'steps':steps,'seed':k,'reference_id':ref['id'] if any(x[0] in ('fda','histogram') for x in steps) else None,'reference_sha256':ref['sha256'] if any(x[0] in ('fda','histogram') for x in steps) else None,'annotations_note':'Source masks and annotations unchanged; no new geometry or annotation outputs created.'})
   rows.append({'path':rel,'engine':source['engine'],'family':source['family'],'condition':name+' / '+level,'label':f"{source['engine']} · {source['family']} · {source['slot']} · {name} {level}",'metadata':meta})
   if source['annotations']:
    a=max(source['annotations'],key=lambda q:(q['bbox'][2]-q['bbox'][0])*(q['bbox'][3]-q['bbox'][1]));x1,y1,x2,y2=map(int,a['bbox']);box=(max(0,x1-10),max(0,y1-10),min(image.shape[1],x2+10),min(image.shape[0],y2+10)); cp='images/crop-'+Path(rel).name;Image.fromarray(image).crop(box).save(gallery/cp)
    rows.append({'path':cp,'engine':source['engine']+' crops','family':source['family'],'condition':name+' / '+level,'label':f"{source['family']} · {source['slot']} · {name} {level} · crop",'metadata':{**meta,'crop_bbox_xyxy':box,'crop_sha256':digest(gallery/cp)}})
  atomic_json(out/'progress.json',{'completed_sources':len({(x['engine'],x['family'],x['slot']) for x in allsrc[:allsrc.index(source)+1]}),'total_sources':len(allsrc),'gallery_cards':len(rows)})
  atomic_json(gallery/'manifest.json',{'title':'Domain adaptation and capture effects: matched screen','images':rows})
 atomic_json(out/'summary.json',{'status':'complete','sources':len(allsrc),'cards':len(rows),'variants_per_source':len(variants),'backend':A.__version__,'refs':[{'id':r['id'],'sha256':r['sha256']} for r in refs],'limitations':['2D source images are JPEGs; JPEG treatment simulates an additional compression cycle.','3D examples are post-render RGB changes and do not create new masks.','Reference images are development backgrounds, not a real-camera or independent holdout.','Forced variants are not frequency estimates or evidence of detector performance.']})

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--worker',action='store_true');a=p.parse_args();out=a.output_dir.resolve()
 if a.worker:worker(out);return
 policy_path=ROOT/'experiments/domain-adaptation-v1/local-warning-policy.json'; policy=Policy.model_validate_json(policy_path.read_bytes()); memory=psutil.virtual_memory();guards=resolve_guards(policy.guards,memory.total,memory.available)
 out.mkdir(parents=True,exist_ok=False);shutil.copy2(__file__,out/'driver-source.py');shutil.copy2(policy_path,out/'policy.json');atomic_json(out/'guard-basis.json',{'available_bytes':memory.available,'total_bytes':memory.total,'swap_out_initial_bytes':psutil.swap_memory().sout,'guards':guards}); result=monitor([[sys.executable,str(Path(__file__).resolve()),'--worker','--output-dir',str(out)]],out,'screen',policy.guards.timeout_seconds,guards);atomic_json(out/'result.json',result)
 if result['status']!='complete':raise RuntimeError(f"{result['status']}: {result['reason']}")
 print(out)
if __name__=='__main__':main()
