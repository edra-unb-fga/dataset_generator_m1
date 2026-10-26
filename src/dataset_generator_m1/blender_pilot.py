"""Optional research harness contracts. Importing this module never imports Blender."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import monotonic
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Treatment(Strict):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    paired_reference: str | None = None
    lighting: Literal['sun', 'environment', 'overcast', 'shade', 'night-single', 'night-mixed'] = 'sun'
    roughness: float = Field(default=.5, ge=0, le=1)
    normal_strength: float = Field(default=.2, ge=0, le=2)
    uv_scale_m: float = Field(default=2, gt=0, le=100)
    uv_rotation_degrees: float = 0
    shadows: bool = True
    occluder: bool = False
    haze_density: float = Field(default=0, ge=0, le=.05)
    exposure_ev: float = Field(default=0, ge=-8, le=8)
    tone: Literal['AgX', 'Standard'] = 'AgX'
    noise_std: float = Field(default=0, ge=0, le=.1)
    aperture_fstop: float = Field(default=8, ge=.7, le=64)
    depth_of_field: bool = False
    focus_distance_m: float | None = Field(default=None, gt=0)
    camera_speed_mps: float = Field(default=0, ge=0, le=20)
    shutter_seconds: float = Field(default=1/60, gt=0, le=1)
    distortion: tuple[float, float, float, float, float] = (0, 0, 0, 0, 0)
    camera_distance_scale: float = Field(default=1, gt=0, le=5)
    camera_roll_degrees: float = Field(default=0, ge=-180, le=180)
    camera_azimuth_degrees: float = Field(default=0, ge=-180, le=180)
    view_degrees: float = Field(default=20, ge=0, le=65)
    sun_elevation_degrees: float = Field(default=45, ge=5, le=90)
    light_power_w: float = Field(default=800, gt=0, le=10000)
    light_size_m: float = Field(default=.7, gt=0, le=10)

    @model_validator(mode='after')
    def bounded_distortion(self):
        if any(abs(v)>.4 for v in self.distortion):
            raise ValueError('Pilot distortion coefficients are bounded to ±0.4')
        return self


class Ground(Strict):
    material_file: Path


class PilotConfig(Strict):
    schema_version: Literal[1] = 1
    seed: int = Field(default=20261026, ge=0)
    reference_pool: Path
    artwork: tuple[Path, Path]
    grounds: tuple[Ground, Ground, Ground]
    environments: tuple[Path, Path]
    width_metres: float = Field(default=1, gt=0, le=10)
    thickness_metres: float = Field(default=.003, gt=0, le=.1)
    resolution: tuple[int, int] = (512, 512)
    focal_length_mm: float = Field(default=35, ge=8, le=150)
    sensor_width_mm: float = Field(default=36, ge=5, le=100)
    principal_point_fraction: tuple[float, float] = (.5, .5)
    threads: int = Field(default=6, ge=1, le=32)
    fast_samples: int = Field(default=32, ge=1, le=1024)
    quality_samples: int = Field(default=128, ge=1, le=4096)
    scenes: int = Field(default=3, ge=1, le=100)
    quality_treatments: tuple[str, ...] = ()
    study_seconds: float = Field(default=7200, gt=0, le=7200)
    treatments: tuple[Treatment, ...]

    @model_validator(mode='after')
    def validate_shape(self):
        if any(not 64<=value<=2048 for value in self.resolution):
            raise ValueError('Pilot resolution is bounded to64–2048 per dimension')
        if any(not 0<=v<=1 for v in self.principal_point_fraction):
            raise ValueError('Principal point fractions must be in[0,1]')
        ids=[t.id for t in self.treatments]
        if not ids or len(ids)!=len(set(ids)):
            raise ValueError('Unique nonempty treatment IDs required')
        if any(t.paired_reference is not None and t.paired_reference not in ids for t in self.treatments):
            raise ValueError('Unknown paired reference treatment')
        if set(self.quality_treatments)-set(ids):
            raise ValueError('Unknown quality treatment')
        if self.quality_samples<self.fast_samples:
            raise ValueError('Quality samples must be at least fast samples')
        return self


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,path)


def load_config(path):
    path=Path(path).resolve()
    config=PilotConfig.model_validate(json.loads(path.read_text()))
    def local(value):return (path.parent/value).resolve()
    return config.model_copy(update={
        'reference_pool':local(config.reference_pool),'artwork':tuple(local(p) for p in config.artwork),
        'environments':tuple(local(p) for p in config.environments),
        'grounds':tuple(g.model_copy(update={'material_file':local(g.material_file)}) for g in config.grounds)})


def reference_scenes(pool):
    from .inspection import inspect_pool
    if inspect_pool(pool)['status']!='valid':raise ValueError('Reference pool failed integrity inspection')
    run=json.loads((pool/'run.json').read_text())
    if run.get('family',{}).get('name')!='landing-pad':
        raise ValueError('Reference must be a landing-pad pool')
    rows=[json.loads(v) for v in (pool/'samples.jsonl').read_text().splitlines() if v]
    if not rows:raise ValueError('A nonempty pinned2D reference pool is required')
    scenes=[];widths=[];counts=[]
    for row in rows:
        objects=[]
        for a in row['annotations']:
            if a['class_name']!='pad':raise ValueError('Blender pilot reference must use pad annotations')
            cx,cy,w,h=a['normalized_bbox']
            widths.append(w)
            objects.append({'center':[cx,cy], 'fraction':w,
                            'angle':a.get('sampled_rotation_degrees',0),
                            'source_sha256':a['source_content_hash']})
        if len(objects)>6:raise ValueError('This bounded pilot supports at most6 pads per scene')
        counts.append(len(objects))
        scenes.append({'objects':objects,'negative':row.get('intentional_negative',False),
                       'reference_image':str((pool/row['image_path']).resolve())})
    if not widths:raise ValueError('Reference pool needs positive pad scenes')
    return scenes,{'samples_sha256':digest_file(pool/'samples.jsonl'),'run_sha256':digest_file(pool/'run.json'),
                   'target_width_fraction_quantiles':np.quantile(widths,[.1,.5,.9]).tolist(),
                   'counts':counts,'images':len(rows)}


def prepare(config_path,output):
    config=load_config(config_path);output=Path(output).resolve()
    scenes,reference=reference_scenes(config.reference_pool)
    assets=[];grounds=[]
    for g in config.grounds:
        record=json.loads(g.material_file.read_text())
        if record.get('license')!='CC0-1.0':raise ValueError('Only declared CC0 materials allowed')
        maps={}
        for role,item in record['maps'].items():
            file=g.material_file.parent/record['asset_id']/(role+'.jpg')
            if digest_file(file)!=item['sha256']:raise ValueError('PBR map hash mismatch')
            maps[role]=str(file.resolve())
        grounds.append({'maps':maps,'provenance':record})
        assets.append({'kind':'ground','manifest':record})
    environments=[]
    for file in config.environments:
        record=json.loads(file.read_text())
        hdr=file.parent/record['path']
        if record.get('license')!='CC0-1.0' or digest_file(hdr)!=record['sha256']:
            raise ValueError('CC0 environment or hash mismatch')
        environments.append(str(hdr.resolve()));assets.append({'kind':'environment','manifest':record})
    artwork=[]
    for file in config.artwork:
        with Image.open(file) as image:
            aspect=image.height/image.width
            if np.asarray(image.convert('RGBA'))[:,:,3].min()!=255:
                raise ValueError('Pilot artwork must be an opaque complete panel')
        artwork.append({'path':str(file),'sha256':digest_file(file),'aspect':aspect})
    by_hash={item['sha256']:index for index,item in enumerate(artwork)}
    for scene in scenes:
        for obj in scene['objects']:
            if obj['source_sha256'] not in by_hash:raise ValueError('Reference artwork revision differs from the physical pilot')
            obj['artwork_index']=by_hash[obj['source_sha256']]
    contract={'config':config.model_dump(mode='json'),'reference':reference,'assets':assets,'artwork':artwork,
              'harness_source_sha256':digest_file(__file__),
              'renderer_script_sha256':digest_file(Path(__file__).resolve().parents[2]/'experiments/blenderproc/render.py')}
    jobs=[]
    for scene_index in range(config.scenes):
        scene=scenes[scene_index%len(scenes)]
        for treatment in config.treatments:
            for quality in ('fast','quality'):
                if quality=='quality' and treatment.id not in (config.quality_treatments or (config.treatments[0].id,)):
                    continue
                # All fast coverage precedes expensive quality comparisons.
                jobs.append({'id':f'{scene_index:03d}-{treatment.id}-{quality}', 'seed':config.seed+scene_index,
                             'scene_index':scene_index,'scene':scene,'treatment':treatment.model_dump(mode='json'),
                             'samples':config.fast_samples if quality=='fast' else config.quality_samples,'quality':quality,
                             'ground_index':scene_index%3,'case':'ordinary',
                             'benchmark':scene_index==0 and treatment.id==config.treatments[0].id})
    first=jobs[0]
    for case in ('negative','clipped','occluded','fully-hidden','overlap','closeup'):
        scene=dict(first['scene'])
        scene['objects']=[] if case=='negative' else list(scene['objects'][:2])
        scene['negative']=case=='negative'
        jobs.append({**first,'id':'diagnostic-'+case,'case':case,'scene':scene,'benchmark':False})
    jobs.sort(key=lambda j:(j['quality']!='fast',j['scene_index']))
    contract['jobs_sha256']=digest(jobs)
    runtime={'artwork':artwork,'grounds':grounds,'environments':environments,'config':config.model_dump(mode='json')}
    contract['runtime_sha256']=digest(runtime)
    identity=digest(contract)
    if output.exists():
        stored=load_study(output)
        if stored['identity']!=identity:raise ValueError('Existing study has a different configuration/source identity')
        return stored
    output.mkdir(parents=True)
    study={'schema_version':1,'identity':identity,'contract':contract,'jobs':jobs,'artwork':artwork,'grounds':grounds,
           'environments':environments,'config':config.model_dump(mode='json')}
    atomic_json(output/'study.json',study)
    return study


def mask_rle(mask):
    flat=np.asarray(mask,dtype=bool).ravel(order='F')
    boundaries=np.flatnonzero(flat[1:]!=flat[:-1])+1
    counts=np.diff(np.r_[0,boundaries,flat.size]).astype(int).tolist()
    if flat.size and flat[0]:counts.insert(0,0)
    return {'size':list(mask.shape),'counts':counts}


def mask_box(mask):
    ys,xs=np.where(mask)
    if not len(xs):return None
    return [int(xs.min()),int(ys.min()),int(xs.max()+1-xs.min()),int(ys.max()+1-ys.min())]


def annotation_rows(visible,full,image_id,first_id=1):
    if visible.shape!=full.shape or visible.ndim!=3:raise ValueError('Matching NxHxW masks required')
    result={'visible':[],'full':[]};next_id=first_id
    for instance,(v,f) in enumerate(zip(visible.astype(bool),full.astype(bool))):
        if np.any(v&~f):raise ValueError('Visible mask exceeds full support')
        support=float(v.sum()/f.sum()) if f.any() else 0
        if 0<support<.25:raise ValueError('below-visible-support-floor')
        if not v.any():continue
        for semantics,mask in (('visible',v),('full',f)):
            result[semantics].append({'id':next_id,'image_id':image_id,'category_id':1,'instance_id':instance,
                'bbox':mask_box(mask),'area':int(mask.sum()),'iscrowd':0,'segmentation':mask_rle(mask),
                'visible_support_fraction':support})
        next_id+=1
    return result


def load_study(root):
    value=json.loads((Path(root)/'study.json').read_text())
    runtime={key:value[key] for key in ('config','artwork','grounds','environments')}
    if (digest(value['contract'])!=value['identity'] or digest(value['jobs'])!=value['contract']['jobs_sha256']
            or digest(runtime)!=value['contract']['runtime_sha256']):
        raise ValueError('Study contract or job plan changed')
    return value


def completed_outputs(root,study):
    rows=[]
    for job in study['jobs']:
        path=root/'scenes'/job['id']
        if not (path/'result.json').exists():continue
        row=json.loads((path/'result.json').read_text())
        if row.get('status') not in {'accepted','rejected'}:raise ValueError('Unknown scene result status')
        if row['status']=='accepted' and set(row.get('files',{}))!={'rgb.png','masks.npz'}:raise ValueError('Incomplete accepted scene files')
        if row.get('identity')!=study['identity'] or row.get('job')!=job:raise ValueError('Stale scene result')
        for file,expected in row.get('files',{}).items():
            if digest_file(path/file)!=expected:raise ValueError('Completed scene checksum mismatch')
        rows.append((job,path,row))
    return rows


def export_study(root, *, yolo=False):
    from .ownership import CoordinatorLease
    with CoordinatorLease(root):
        result=_export_coco(root)
        if yolo:result['yolo']=_export_yolo(root)
        return result


def export_coco(root):
    return export_study(root)


def _export_coco(root):
    export_started=monotonic()
    root=Path(root).resolve();study=load_study(root)
    images=[];annotations={'visible':[],'full':[]};metadata={};next_id=1
    for image_id,(job,path,row) in enumerate(completed_outputs(root,study),1):
        if row['status']!='accepted':continue
        with np.load(path/'masks.npz',allow_pickle=False) as masks:
            converted=annotation_rows(masks['visible'],masks['full'],image_id,next_id)
        next_id+=len(converted['visible'])
        if not converted['visible'] and not job['scene']['negative']:raise ValueError('Accidental empty positive')
        with Image.open(path/'rgb.png') as image:width,height=image.size
        images.append({'id':image_id,'file_name':str((path/'rgb.png').relative_to(root)), 'width':width,'height':height})
        for semantics in annotations:annotations[semantics].extend(converted[semantics])
        metadata[str(image_id)]={'synthetic_pipeline':'blenderproc','study_identity':study['identity'],
            'conditions':job,'render_evidence':row,'configured_scale':'nominal, not calibrated',
            'mask_policy':'sharp reference-pose geometry; 25% in-frame visible-support floor'}
    if not images:raise ValueError('No accepted completed scenes to export')
    atomic_json(root/'metadata.json',metadata)
    for semantics in annotations:
        atomic_json(root/f'coco-{semantics}.json',{'images':images,'annotations':annotations[semantics],
                    'categories':[{'id':1,'name':'pad'}]})
        atomic_json(root/f'evaluation-{semantics}.json',{'schema_version':1,'format':'coco','domain':'synthetic',
            'role':'development','annotation_semantics':semantics,'source':'.',
            'ground_truth':f'coco-{semantics}.json','images_root':'.','metadata_file':'metadata.json',
            'training_provenance':{'status':'not-trained','purpose':'engineering comparison'}})
    result={'images':len(images),'instances':len(annotations['visible']),'export_seconds':monotonic()-export_started}
    atomic_json(root/'coco-export.json',result)
    return result


def validate_inputs(study,renderer):
    """Refuse mutable external inputs/source before any new render or resume."""
    contract=study['contract']
    expected=[(Path(__file__),contract['harness_source_sha256']),
              (renderer,contract['renderer_script_sha256'])]
    expected.extend((item['path'],item['sha256']) for item in study['artwork'])
    for ground in study['grounds']:
        expected.extend((path,ground['provenance']['maps'][role]['sha256']) for role,path in ground['maps'].items())
    manifests=[a['manifest'] for a in contract['assets'] if a['kind']=='environment']
    expected.extend((path,record['sha256']) for path,record in zip(study['environments'],manifests,strict=True))
    reference=Path(study['config']['reference_pool'])
    expected.extend((reference/name,contract['reference'][key]) for name,key in
                    (('run.json','run_sha256'),('samples.jsonl','samples_sha256')))
    for path,sha in expected:
        if digest_file(path)!=sha:raise ValueError('Prepared source/input changed; prepare a fresh study: '+str(path))
    # Also check referenced pool images/masks via its canonical integrity inspector.
    reference_scenes(reference)


def run_study(root,blenderproc,blender_install_path,*,job_ids=None):
    from .ownership import CoordinatorLease
    with CoordinatorLease(root):
        return _run_study(root,blenderproc,blender_install_path,job_ids=job_ids)


def _run_study(root,blenderproc,blender_install_path,*,job_ids=None):
    """One isolated Blender session; guards apply to its complete descendant tree."""
    import psutil
    import signal
    root=Path(root).resolve();study=load_study(root)
    renderer=Path(__file__).resolve().parents[2]/'experiments/blenderproc/render.py'
    validate_inputs(study,renderer)
    completed=completed_outputs(root,study)  # Verify checkpoint hashes before asking Blender to skip them.
    if (root/'coco-export.json').exists():
        selected=set(job_ids or [j['id'] for j in study['jobs']])
        if selected-{j['id'] for j,p,r in completed}:
            raise ValueError('Exported study is frozen; prepare a fresh study before adding scenes')
    previous=json.loads((root/'runs.json').read_text()) if (root/'runs.json').exists() else []
    remaining=study['config']['study_seconds']-sum(r['command_seconds'] for r in previous)
    if remaining<=0:raise ValueError('Study rendering budget already exhausted')
    selected=set(job_ids or [j['id'] for j in study['jobs']])
    if not selected.issubset({j['id'] for j in study['jobs']}):raise ValueError('Unknown job IDs')
    command=[str(Path(blenderproc).resolve()),'run',str(renderer),str(root/'study.json'),
             '--blender-install-path',str(Path(blender_install_path).resolve()),
             '--temp-dir',str(root/'blender-temp'),'--jobs',*sorted(selected)]
    started=monotonic();initial_swap=psutil.swap_memory().sout;observations=[];reason=None
    with (root/f'run-{len(previous):02d}.log').open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name=='posix',
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','BLENDER_USER_CONFIG':str(root/'blender-user-config')})
        try:
            while True:
                available=psutil.virtual_memory().available;swap=psutil.swap_memory().sout-initial_swap
                try:
                    parent=psutil.Process(process.pid);tree=[parent,*parent.children(recursive=True)]
                except psutil.Error:tree=[]
                rss=0
                for child in tree:
                    try:rss+=child.memory_info().rss
                    except psutil.Error:pass
                elapsed=monotonic()-started
                observations.append({'seconds':elapsed,'rss_bytes':rss,'available_bytes':available,'swap_out_delta_bytes':swap})
                reason=('available-memory-floor' if available<2*2**30 else 'process-tree-RSS' if rss>10*2**30 else
                        'host-swap-out' if swap>16*2**20 else 'study-time-budget' if elapsed>=remaining else None)
                atomic_json(root/'progress.json',{'status':'running','elapsed_seconds':elapsed,'remaining_budget_seconds':max(0,remaining-elapsed),
                            'completed_scenes':len(list((root/'scenes').glob('*/result.json')))})
                if reason:break
                try:code=process.wait(timeout=.25);break
                except subprocess.TimeoutExpired:pass
        except KeyboardInterrupt:
            reason='keyboard-interrupted'
        except Exception as error:
            reason='monitor-failed: '+type(error).__name__
        finally:
            if process.poll() is None:
                try:children=psutil.Process(process.pid).children(recursive=True)
                except psutil.Error:children=[]
                try:
                    if os.name=='posix':os.killpg(process.pid,signal.SIGTERM)
                    else:process.terminate()
                except ProcessLookupError:pass
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                for child in children:
                    try:child.kill()
                    except psutil.Error:pass
                psutil.wait_procs(children,timeout=3)
    code=process.returncode
    record={'status':'budget-limited' if reason=='study-time-budget' else 'interrupted' if reason=='keyboard-interrupted' else 'guard-aborted' if reason else 'complete' if code==0 else 'failed',
            'reason':reason,'returncode':code,'command_seconds':monotonic()-started,'selected_jobs':sorted(selected),
            'peak_rss_bytes':max((v['rss_bytes'] for v in observations),default=0),'minimum_available_bytes':min((v['available_bytes'] for v in observations),default=None),
            'swap_out_delta_bytes':max((v['swap_out_delta_bytes'] for v in observations),default=0),
            'guards':{'min_available_gib':2,'rss_limit_gib':10,'max_swap_out_mib':16}}
    atomic_json(root/f'run-{len(previous):02d}-resources.json',observations)
    previous.append(record);atomic_json(root/'runs.json',previous);atomic_json(root/'progress.json',record)
    return record


def export_yolo(root):
    from .ownership import CoordinatorLease
    with CoordinatorLease(root):
        return _export_yolo(root)


def _export_yolo(root):
    """Optional bounded conversion. Never publish a partially labeled dataset."""
    from .annotation_evidence import polygonize_coverage
    root=Path(root);coco=json.loads((root/'coco-visible.json').read_text())
    mapping={c['id']:index for index,c in enumerate(coco['categories'])}
    statuses={};fidelity=[];started=monotonic()
    for task in ('detection','segmentation'):
        target=root/f'yolo-{task}'
        if target.exists():raise ValueError('YOLO output already exists')
        try:
            with tempfile.TemporaryDirectory(dir=root) as temporary:
                staging=Path(temporary);(staging/'images').mkdir();(staging/'labels').mkdir()
                by_image={row['id']:[] for row in coco['images']}
                for a in coco['annotations']:by_image[a['image_id']].append(a)
                for row in coco['images']:
                    if monotonic()-started>300:raise ValueError('Optional conversion five-minute budget exceeded')
                    width,height=row['width'],row['height'];lines=[]
                    for a in by_image[row['id']]:
                        cls=mapping[a['category_id']]
                        if task=='detection':
                            x,y,w,h=a['bbox'];values=[(x+w/2)/width,(y+h/2)/height,w/width,h/height]
                        else:
                            from .evaluation_io import instance_mask
                            mask=instance_mask(a['segmentation'],width,height)
                            # Bound pairwise disconnected-contour merging before calling shared helper.
                            contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
                            if sum(len(v) for v in contours)>2000:raise ValueError('Mask exceeds optional contour-complexity budget')
                            p=polygonize_coverage(mask.astype(np.uint8)*255,alpha_threshold=8)
                            values=[v/(width if index%2==0 else height) for index,v in enumerate(np.asarray(p.polygon).ravel())]
                            serialized=np.asarray([float(f'{v:.6f}') for v in values]).reshape(-1,2)*[width,height]
                            reconstructed=np.zeros(mask.shape,dtype=np.uint8);cv2.fillPoly(reconstructed,[np.rint(serialized).astype(np.int32)],1)
                            union=np.logical_or(mask,reconstructed).sum()
                            fidelity.append({'annotation_id':a['id'],'components':p.components,'holes':p.holes,
                                'serialized_iou':float(np.logical_and(mask,reconstructed).sum()/union),
                                'serialized_area_error':float(abs(int(mask.sum())-int(reconstructed.sum()))/max(1,int(mask.sum()))),
                                'warnings':list(p.warnings)})
                        if not all(np.isfinite(values)) or not all(0<=v<=1 for v in values):raise ValueError('Invalid normalized YOLO label')
                        lines.append(str(cls)+' '+' '.join(f'{v:.6f}' for v in values))
                    shutil.copy2(root/row['file_name'],staging/'images'/f'{row["id"]}.png')
                    (staging/'labels'/f'{row["id"]}.txt').write_text('\n'.join(lines)+ ('\n' if lines else ''))
                import yaml
                (staging/'data.yaml').write_text('# Development export: train/val alias the same images; no independent validation.\n'+yaml.safe_dump({'path':'.','train':'images','val':'images','names':{i:c['name'] for i,c in enumerate(coco['categories'])}}))
                atomic_json(staging/'provenance.json',{'canonical_coco_sha256':digest_file(root/'coco-visible.json'),
                    'annotation_semantics':'visible geometric reference','split_policy':'single development set; train/val aliases are NOT independent evaluation'})
                os.rename(staging,target)
            statuses[task]={'status':'complete','images':len(coco['images'])}
        except (ValueError,RuntimeError) as error:
            statuses[task]={'status':'unavailable','reason':str(error)}
    atomic_json(root/'yolo-conversion.json',{'formats':statuses,'fidelity':fidelity})
    return statuses


def report(root):
    import html
    root=Path(root);study=load_study(root);rows=completed_outputs(root,study)
    accepted=[item for item in rows if item[2]['status']=='accepted'];cards=[]
    for job,path,result in accepted:
        image=Image.open(path/'rgb.png').convert('RGB');image.thumbnail((240,240))
        tile=Image.new('RGB',(256,280),'white');tile.paste(image,((256-image.width)//2,25));draw=ImageDraw.Draw(tile)
        draw.text((4,3),job['id'],fill='black');draw.text((4,258),f'{result["total_seconds"]:.1f}s including labels',fill='black');cards.append(tile)
    if cards:
        columns=4;sheet=Image.new('RGB',(columns*256,((len(cards)+columns-1)//columns)*280),'#dddddd')
        for index,tile in enumerate(cards):sheet.paste(tile,((index%columns)*256,(index//columns)*280))
        sheet.save(root/'contact-sheet.jpg')
    values=[]
    first_treatment=study['config']['treatments'][0]['id']
    for job,path,row in accepted:
        if job['case']!='ordinary' or job['quality']!='fast' or job['treatment']['id']!=first_treatment:continue
        with np.load(path/'masks.npz',allow_pickle=False) as masks:
            for mask in masks['visible']:
                box=mask_box(mask)
                if box:values.append(box[2]/mask.shape[1])
    summary={'identity':study['identity'],'accepted':len(accepted),'rejected':len(rows)-len(accepted),
             'planned':len(study['jobs']),'reference':study['contract']['reference'],
             'achieved_baseline_width_fraction_quantiles':np.quantile(values,[.1,.5,.9]).tolist() if values else None,
             'runs':json.loads((root/'runs.json').read_text()) if (root/'runs.json').exists() else [],
             'costs':[{'job':j['id'],'setup_and_attempts':r['attempts'],'rgb_render_seconds':r['rgb_render_seconds'],
                       'warm_same_scene_render_seconds':r['warm_same_scene_render_seconds'],'total_seconds':r['total_seconds'],'accepted_output_seconds':r.get('accepted_output_seconds',r['total_seconds'])} for j,p,r in accepted],
             'limits':['Nominal materials/camera; no calibration or model benefit measured.',
                       'Geometric labels remain sharp under RGB blur. Lens distortion is a post-render warp.',
                       'Noise is a post-display RGB approximation, not a physical sensor model.',
                       'Low sample counts are exploratory; no universal renderer speed ratio.']}
    atomic_json(root/'summary.json',summary)
    baseline={(j['scene_index'],j['quality'],j['treatment']['id']):p for j,p,r in accepted if j['case']=='ordinary'}
    gallery=[]
    for job,path,row in accepted:
        rgb=np.asarray(Image.open(path/'rgb.png').convert('RGB')).copy()
        with np.load(path/'masks.npz',allow_pickle=False) as masks:
            for index,mask in enumerate(masks['visible']):
                contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(rgb,contours,-1,(0,255,100),1)
                box=mask_box(mask)
                if box:cv2.putText(rgb,str(index),(box[0],max(10,box[1])),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
        Image.fromarray(rgb).save(path/'qa.png')
        if job['scene_index']==0 and job['quality']=='fast':
            relative=path.relative_to(root).as_posix()
            base=baseline.get((job['scene_index'],job['quality'],job['treatment'].get('paired_reference') or first_treatment))
            before='' if base is None else f'<a href="{base.relative_to(root).as_posix()}/rgb.png"><img width="320" src="{base.relative_to(root).as_posix()}/rgb.png" alt="Base reference"></a>'
            gallery.append(f'<h3>{html.escape(job["id"])}</h3>'+before+f'<a href="{relative}/rgb.png"><img width="320" src="{relative}/rgb.png" alt="Treatment"></a> <a href="{relative}/qa.png">Mask overlay</a>')
    # Cost bars retain all observed scene values; no confidence intervals inferred.
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        ids=[t['id'] for t in study['config']['treatments']]
        groups={key:[r for j,p,r in accepted if j['case']=='ordinary' and j['quality']=='fast' and j['treatment']['id']==key] for key in ids}
        ids=[key for key in ids if groups[key]]
        fig,axes=plt.subplots(1,2,figsize=(12,max(4,len(ids)*.3)),layout='constrained')
        for ax,key,label in zip(axes,('rgb_render_seconds','accepted_output_seconds'),('RGB render seconds','Complete accepted output seconds')):
            vals=[[r.get(key,r['total_seconds']) for r in groups[name]] for name in ids]
            ax.barh(ids,[float(np.median(v)) for v in vals],color='#476b82')
            for y,v in enumerate(vals):ax.scatter(v,[y]*len(v),s=12,color='#d89438')
            ax.set_xlabel(label);ax.invert_yaxis();ax.spines[['top','right']].set_visible(False)
        fig.suptitle('Fast settings: median bars and observed scene costs (no confidence intervals)')
        fig.savefig(root/'costs.png',dpi=140);plt.close(fig)
    except ImportError:
        pass
    body='<h1>Targeted BlenderProc pilot</h1><p>'+html.escape(' '.join(summary['limits']))+'</p>'
    body+='<p>'+html.escape(f'Accepted {len(accepted)} / planned {len(study["jobs"])}; inspect summary.json for timing and rejection denominators.')+'</p>'
    if cards:body+='<img src="contact-sheet.jpg" alt="Controlled material lighting and camera views" style="max-width:100%">'
    body+='<table><tr><th>Scene</th><th>RGB s</th><th>Complete s</th></tr>'
    for job,path,row in accepted:body+=f'<tr><td>{html.escape(job["id"])}</td><td>{row["rgb_render_seconds"]:.3f}</td><td>{row["total_seconds"]:.3f}</td></tr>'
    body+='</table>'
    if (root/'costs.png').exists():body+='<img src="costs.png" alt="RGB and full output costs" style="max-width:100%">'
    body+='<h2>Paired scene0 views: base / treatment</h2>'+''.join(gallery)
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>BlenderProc pilot</title>'+body)
    return summary


def fetch_assets(manifest_dir,output):
    """Acquire only the small reviewed hash-pinned CC0 set, with bounded existing downloads."""
    from .materials import fetch_material, download_bytes
    output=Path(output);output.mkdir(parents=True,exist_ok=True);results=[]
    for file in sorted(Path(manifest_dir).glob('*.json')):
        item=json.loads(file.read_text())
        if item.get('license')!='CC0-1.0':raise ValueError('Non-CC0 pilot asset')
        if 'maps' in item:
            results.append(fetch_material(item,output))
        else:
            target=output/item['path']
            if target.exists():
                if digest_file(target)!=item['sha256']:raise ValueError('Existing HDR hash mismatch')
            else:
                data=download_bytes(item['url'])
                if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Downloaded HDR hash mismatch')
                temporary=target.with_suffix('.tmp');temporary.write_bytes(data);os.replace(temporary,target)
            results.append({'asset_id':item['asset_id'],'path':str(target)})
        destination=output/file.name
        if destination.exists() and json.loads(destination.read_text())!=item:raise ValueError('Asset selection already differs')
        atomic_json(destination,item)
    if len(results)!=5:raise ValueError('Expected the reviewed3 ground +2 environment manifests')
    return results


def bridge_composers(assets_dir,foreground_dir,output,*,workers=1):
    """Normal2D composers using the physical pilot's same color maps and artwork."""
    import yaml
    repository=Path(__file__).resolve().parents[2]
    assets_dir=Path(assets_dir).resolve();foreground_dir=Path(foreground_dir).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Fresh composer output directory required')
    if not 1<=workers<=32:raise ValueError('workers must be1–32')
    output.mkdir(parents=True)
    mixing=output/'mixing.yaml';mixing.write_text(yaml.safe_dump({'schema_version':1,'subject':'background_mixing','value':{'recipe_weights':{'planar':1.0}}}))
    paths=[]
    for mode in ('pristine','surface'):
        value=yaml.safe_load((repository/'examples/configs/landing-pad_minimal.yaml').read_text())
        value['background_mixing']=str(mixing)
        value['appearance']={'preset':'builtin:appearance/'+('no-appearance' if mode=='pristine' else 'surface-camera')}
        value['inline']={'assets':{'backgrounds':{'paths':[str(assets_dir/name/'color.jpg') for name in ('Ground068','Asphalt012','Concrete034')],'recursive':False},
            'foregrounds':{'paths':[str(foreground_dir)],'recursive':True}},
            'background_recipes':{'recipe_file':str(repository/'examples/configs/texture_recipes.yaml')},
            'output':{'image_format':'png'},
            'execution':{'workers':workers,'native_threads':1,'max_in_flight':workers,'decoded_cache_mb':0},
            'reporting':{'qa_samples':2}}
        if mode=='surface':value['inline']['scene']={'foreground_resampling':'premultiplied','lighting':{'source_assumption':'unlit-approximation'}}
        path=output/(mode+'.yaml');path.write_text(yaml.safe_dump(value,sort_keys=False));paths.append(str(path))
    return paths
