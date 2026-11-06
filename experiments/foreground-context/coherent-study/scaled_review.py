"""Bounded matched fixed-vs-scaled motion review; forced cells are diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import psutil
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from dataset_generator_m1.blender_runner import monitor
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.models import ExecutionConfig, GenerationProfile
from guarded_effect_combinations import Policy, resolve_guards
from study_surface_2d import atomic_json, run_pool
from build_scene_review_gallery import build

FAMILIES = ('landing-pad', 'landing', 'manometro')
GROUPS = ('asphalt_ground', 'concrete_ground', 'dirt_ground', 'grass', 'gravel', 'wood', 'tiled_ground', 'chipboard')
CASES = (('forced-severe',15),('forced-severe',15),('forced-moderate',7),('forced-moderate',7),('forced-mild',3),('motion-disabled',0),('natural',None),('natural',None))
ACK = {'REALISTIC_HEAVY_COST', 'UNCALIBRATED_COHERENT_APPEARANCE', 'UNCALIBRATED_COHERENT_SCENE', 'EXPERIMENTAL_SCENE_LIGHTING_UNCALIBRATED', 'EXPERIMENTAL_FOREGROUND_CONTEXT_UNCALIBRATED'}
POLICY = ROOT / 'experiments/foreground-context/coherent-study/one-worker-policy.json'


def cross_resolution_evidence(small, large, family, index):
    """Compare normalized scene and target projections, allowing raster rounding."""
    a=np.array(small['scene_to_output']); b=np.array(large['scene_to_output'])
    transform=np.diag([2,2,1]); expected=transform@a@np.linalg.inv(transform)
    scene_error=float(np.max(np.abs(b/b[2,2]-expected/expected[2,2])))
    left={v['instance_id']:v for v in small['annotations']}
    right={v['instance_id']:v for v in large['annotations']}
    same_instances=set(left)==set(right)
    objects=[]
    for key in sorted(set(left)&set(right)):
        x,y=left[key],right[key]
        # asset_to_output starts from the already resized/rotated foreground
        # raster, whose coordinates double along with the output resolution.
        expected=transform@np.array(x['asset_to_output'])@np.linalg.inv(transform); actual=np.array(y['asset_to_output'])
        matrix_error=float(np.max(np.abs(actual/actual[2,2]-expected/expected[2,2])))
        box_error=float(np.max(np.abs(np.array(y['bbox'])/2-np.array(x['bbox']))))
        objects.append({'instance_id':key,'same_asset':x['source_content_hash']==y['source_content_hash'],
                        'matrix_error':matrix_error,'box_error_at_640':box_error})
    same_sources=[s['content_hash'] for s in small['background']['sources']]==[s['content_hash'] for s in large['background']['sources']]
    passed=(same_sources and same_instances and scene_error<=1e-3 and
            all(v['same_asset'] and v['matrix_error']<=1.1 and v['box_error_at_640']<=2 for v in objects))
    return {'family':family,'case':index,'status':'pass' if passed else 'review-needed',
            'scene_homography_error':scene_error,'same_background_sources':same_sources,
            'same_instances':same_instances,'objects':objects,
            'scene_matrix_tolerance':1e-3,'foreground_matrix_tolerance':1.1,'box_tolerance_at_640':2}


def profile(root, family, variant, size, index, seed):
    composer = yaml.safe_load((ROOT / f'examples/configs/{family}_minimal.yaml').read_text())
    composer['scene'] = 'builtin:scene/coherent-varied'
    appearance = 'coherent-balanced' + ('-scaled' if variant == 'scaled' else '') + ('-manometro' if family == 'manometro' else '')
    composer['appearance'] = {'preset': 'builtin:appearance/' + appearance}
    path = root / 'composers' / f'{family}-{variant}.yaml'
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(composer, sort_keys=False))
    base = load_profile(path)
    values = base.profile.model_dump(mode='json')
    values['run'].update(seed=seed, num_images=1)
    values['output']['image_size'] = [size,size]
    values['execution'] = ExecutionConfig(workers=1,native_threads=1).model_dump(mode='json')
    values['assets']['backgrounds']['group_weights'] = {GROUPS[index]:1.0}
    # Sample one of three narrow strata within the family's existing scale bounds.
    lo, hi = values['sampling']['foreground_size']
    a = (0.02,0.40,0.78)[index % 3]; b = (0.20,0.60,0.98)[index % 3]
    values['sampling']['foreground_size'] = [lo+(hi-lo)*a,lo+(hi-lo)*b]
    light = values['scene']['lighting']
    light['shade']['probability'] = 0.0
    light['directional_shade']['probability'] = 1.0 if index % 2 == 0 else 0.0
    kind,kernel = CASES[index]
    for effect in values['appearance']['final']:
        if effect['type'] == 'WeightedMotionBlur' and kernel is not None:
            effect['probability'] = 0.0 if kernel == 0 else 1.0
            if kernel:
                effect['params'] = {'kernels':[kernel], 'weights':[1], **({'reference_size':640} if variant == 'scaled' else {})}
    result=GenerationProfile.model_validate(values)
    return base.model_copy(update={'profile':result, 'contract_hash':digest({'base':base.contract_hash,'review':values}),
        'applied_overrides': {'scaled_review':{'case':index,'kind':kind,'group':GROUPS[index],'shade_forced':index%2==0}}})


def worker(root, seed, sizes):
    records=[]
    for family in FAMILIES:
      for index,(kind,kernel) in enumerate(CASES):
       for size in sizes:
        pairs={}
        for variant in ('fixed','scaled'):
         current=profile(root,family,variant,size,index,seed+index)
         name=f'{family}-{index:02d}-{size}-{variant}'
         atomic_json(root/'profiles'/f'{name}.json',{'profile':current.profile.model_dump(mode='json'), 'source_hashes':current.source_hashes,'contract_hash':current.contract_hash,'software':software_identity()})
         summary,inspection,plan,prep,wall,signature,rows=run_pool(current,root/name,root/'observations.jsonl',acknowledged_codes=ACK)
         row=rows[0]; file=root/name/row['image_path']; image_hash=hashlib.sha256(file.read_bytes()).hexdigest()
         record={'family':family,'case':index,'kind':kind,'configured_kernel':kernel,'shade_forced':index%2==0,'size_stratum':('small','typical','close')[index%3],'size':size,'variant':variant,'seed':seed+index,'source_group':GROUPS[index],'signature':signature,'image_sha256':image_hash,'pool':name,'image_path':row['image_path'],'profile_path':f'profiles/{name}.json','sample':row,'generation_seconds':wall}
         records.append(record); pairs[variant]=record
         atomic_json(root/'records.json',records)
        if pairs['fixed']['signature'] != pairs['scaled']['signature']:
            raise RuntimeError(f'{family} case {index} size {size}: paired geometry/masks differ')
        first=pairs['fixed']['sample']['background']; second=pairs['scaled']['sample']['background']
        if (first['recipe_id'], first['sampled_parameters'], [s['content_hash'] for s in first['sources']]) != (second['recipe_id'], second['sampled_parameters'], [s['content_hash'] for s in second['sources']]):
            raise RuntimeError(f'{family} case {index} size {size}: paired backgrounds differ')
        if size==640 and pairs['fixed']['image_sha256']!=pairs['scaled']['image_sha256']:
            raise RuntimeError(f'{family} case {index}: 640px image equivalence failed')
    # Compare normalized coordinate transforms across resolutions for each family/case.
    cross=[]
    for family in FAMILIES if set(sizes)=={640,1280} else ():
     for index in range(len(CASES)):
      small=next(r for r in records if (r['family'],r['case'],r['size'],r['variant'])==(family,index,640,'fixed'))
      large=next(r for r in records if (r['family'],r['case'],r['size'],r['variant'])==(family,index,1280,'fixed'))
      cross.append(cross_resolution_evidence(small['sample'],large['sample'],family,index))
    status=('partial' if len(sizes)!=2 else 'review-needed' if any(r['status']!='pass' for r in cross) else 'complete')
    atomic_json(root/'summary.json',{'status':status,'images':len(records),'cross_resolution':cross,
      'limitations':['Cases force background group, target size strata, shadow activation and most blur severity; they are not frequency estimates.', 'Natural cases reuse synthetic assets. Source composition and seed are shared; this is not real-world validation.']})
    if status=='review-needed':raise RuntimeError('Cross-resolution projection or source comparison requires review')


def make_gallery(root, output):
    records=json.loads((root/'records.json').read_text()); output.mkdir(parents=True,exist_ok=False)
    recheck_path=root/'cross-resolution-recheck.json'
    recheck=json.loads(recheck_path.read_text()) if recheck_path.exists() else None
    if recheck:shutil.copyfile(recheck_path,output/'cross-resolution-recheck.json')
    rows=[]
    for r in records:
        source=root/r['pool']/r['image_path']; name=r['pool']+source.suffix
        target=output/'images'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=r['image_sha256']:raise ValueError('source checksum mismatch')
        pr=output/r['profile_path'];pr.parent.mkdir(exist_ok=True);shutil.copyfile(root/r['profile_path'],pr)
        meta={k:v for k,v in r.items() if k!='sample'};meta['sample']=r['sample'];meta['profile_file']=r['profile_path']
        if recheck:
            meta['cross_resolution_verification']=next(item for item in recheck['results'] if item['family']==r['family'] and item['case']==r['case'])
        label=f"{r['family']} · case {r['case']} · {r['kind']} · {r['size']} · {r['variant']} · {r['source_group']} · {r['size_stratum']} scale · shade activation {'forced' if r['shade_forced'] else 'disabled'}"
        entry={'path':'images/'+name,'engine':'2D full','family':r['family'],'condition':r['kind'],'label':label,'metadata':meta}
        rows.append(entry)
        annotations=r['sample'].get('annotations',[])
        if annotations:
            box=max(annotations,key=lambda x:(x['bbox'][2]-x['bbox'][0])*(x['bbox'][3]-x['bbox'][1]))['bbox']
            with Image.open(target) as image:
                margin=max(10,r['size']//64);x1,y1,x2,y2=map(int,box)
                crop=image.crop((max(0,x1-margin),max(0,y1-margin),min(image.width,x2+margin),min(image.height,y2+margin)))
                cropname='crop-'+name;crop.save(output/'images'/cropname)
            crop_hash=hashlib.sha256((output/'images'/cropname).read_bytes()).hexdigest()
            crop_meta={**meta,'parent_image_sha256':r['image_sha256'],'image_sha256':crop_hash,'crop_sha256':crop_hash,
                       'crop_bbox_xyxy':[max(0,x1-margin),max(0,y1-margin),min(image.width,x2+margin),min(image.height,y2+margin)]}
            rows.append({**entry,'path':'images/'+cropname,'engine':'2D crop','label':label+' · largest target crop','metadata':crop_meta})
    manifest={'title':'Fixed and scaled capture: final review','images':rows}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    build(output/'manifest.json',output/'index.html')
    if recheck:
        page=output/'index.html';content=page.read_text();anchor='<div id="filters"></div>'
        notice=('<p><strong>Cross-resolution review needed:</strong> the original comparison used the wrong foreground coordinate convention. '
                'The corrected recheck found one landing case with an object accepted at 640 and rejected at 1280 near the visibility threshold. '
                '<a href="cross-resolution-recheck.json">Inspect the corrected verification</a>. Within-resolution pairs passed their geometry and mask checks.</p>')
        if content.count(anchor)!=1:raise ValueError('Unexpected gallery template')
        page.write_text(content.replace(anchor,notice+anchor))
    print(f'Gallery: {len(records)} images, {len(rows)} cards',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--seed',type=int,default=20261107);p.add_argument('--sizes',nargs='+',type=int,choices=(640,1280),default=[640,1280]);p.add_argument('--worker',action='store_true');p.add_argument('--gallery',type=Path)
    a=p.parse_args();root=a.output_dir.resolve()
    if a.gallery: make_gallery(root,a.gallery.resolve());return
    if len(set(a.sizes))!=len(a.sizes):p.error('sizes must be unique')
    if a.worker: worker(root,a.seed,a.sizes);return
    policy=Policy.model_validate_json(POLICY.read_bytes());mem=psutil.virtual_memory();guards=resolve_guards(policy.guards,mem.total,mem.available)
    root.mkdir(parents=True,exist_ok=False);(root/'profiles').mkdir();shutil.copyfile(__file__,root/'driver-source.py');shutil.copyfile(POLICY,root/'policy.json')
    estimates={f'{family}-{size}':plan_execution(profile(root,family,'scaled',size,0,a.seed)).estimated_peak_bytes for family in FAMILIES for size in a.sizes}
    atomic_json(root/'guard-basis.json',{'total_bytes':mem.total,'available_bytes':mem.available,'guards':guards,'estimated_peak_bytes':estimates})
    if max(estimates.values()) > guards['rss_limit_gib']*2**30:
        raise RuntimeError('Available-memory reserve leaves less than the estimated process-tree RSS; do not start this study')
    command=[sys.executable,str(Path(__file__).resolve()),'--worker','--output-dir',str(root),'--seed',str(a.seed),'--sizes',*[str(size) for size in a.sizes]]
    atomic_json(root/'invocation.json',{'command':command,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    outcome=monitor([command],root,'study',policy.guards.timeout_seconds,guards);atomic_json(root/'result.json',outcome)
    if outcome['status']!='complete':raise RuntimeError(f"Study stopped: {outcome['reason']}")
    print(root,flush=True)

if __name__=='__main__':main()
