"""Paired planar attribution + rotating-order production study. Raw evidence stays ignored.

Run paired, production, then report with the same output directory. No model/training claims.
"""
import argparse
from collections import Counter
from dataclasses import replace
import json
import hashlib
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter

import cv2
import numpy as np
from PIL import Image, ImageDraw
import psutil
import yaml

from dataset_generator_m1.analysis_reports import write_report
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import execution_scope, plan_execution
from dataset_generator_m1.identities import digest, generation_identity, software_identity
from dataset_generator_m1.models import AppearanceConfig, SceneLightingConfig, SceneOcclusionConfig, TransformSpec
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer, SceneRejected, derive_seed

TREATMENTS = ['pristine','light-only','wear-only','capture-only','surface','occlusion']


def configured(base, name, forced=False):
    capture = load_profile('examples/configs/landing-pad_surface.yaml').profile.appearance
    wear = tuple(v.model_copy(update={'probability':1.,'params':{'fade':.2,'dirt':.5,'scratches':.4,'marks':24}}) if forced else v for v in capture.foreground)
    final = tuple(v.model_copy(update={'probability':1.}) if forced else v for v in capture.final)
    appearance = AppearanceConfig(foreground=wear if name in ('wear-only','surface','occlusion') else (),
                                  final=final if name in ('capture-only','surface','occlusion') else ())
    lighting = SceneLightingConfig(probability=1.,gain=(.7,.7),gradient=(.4,.4)) if forced else SceneLightingConfig()
    occlusion = SceneOcclusionConfig(probability=1.,count=(32,32),length_fraction=(.1,.35),width_fraction=(.02,.05)) if forced else SceneOcclusionConfig()
    scene = base.profile.scene.model_copy(update={'lighting':lighting if name in ('light-only','surface','occlusion') else None,
                                                 'occlusion':occlusion if name=='occlusion' else None})
    return base.model_copy(update={'profile':base.profile.model_copy(update={'appearance':appearance,'scene':scene})})


def mask_identity(rendered):
    return digest({'ids':[a.instance_id for a in rendered.annotations], 'boxes':[a.bbox for a in rendered.annotations],
                   'full':[hashlib.sha256(m.tobytes()).hexdigest() for m in rendered.full_coverages],
                   'visible':[hashlib.sha256(m.tobytes()).hexdigest() for m in rendered.visible_coverages]})


def montage(root, phase, names, slots):
    cell=256
    sheet=Image.new('RGB',(cell*len(names),(cell+36)*len(slots)+30),'#f1f2ec')
    draw=ImageDraw.Draw(sheet)
    draw.text((10,8),f'{phase}: identical scene inputs; occlusion may change labels',(15,30,40))
    for row,slot in enumerate(slots):
        for col,name in enumerate(names):
            path=root/'paired'/phase/f'{slot:03d}-{name}.jpg'
            x,y=col*cell,30+row*(cell+36)
            if path.exists():
                image=Image.open(path);image.thumbnail((cell,cell));sheet.paste(image,(x,y))
            draw.text((x+5,y+cell+5),f'{name} / slot {slot}',(15,30,40))
    path=root/f'{phase}-paired.jpg';sheet.save(path,quality=90)
    return path.name


def source_identity():
    commit=subprocess.run(['git','rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    dirty=bool(subprocess.run(['git','status','--porcelain'],check=True,capture_output=True,text=True).stdout.strip())
    return {'commit':commit,'dirty':dirty,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def paired(args):
    root=args.output_dir
    if root.exists(): raise ValueError('Paired study destination must be fresh')
    root.mkdir(parents=True)
    raw=yaml.safe_load(args.config.read_text())
    raw['inline']={**raw.get('inline',{}),'output':{'image_size':[512,512]},'execution':{'workers':1,'native_threads':1,'decoded_cache_mb':0},'reporting':{'qa_samples':0}}
    source=root/'paired-input.yaml';source.write_text(yaml.safe_dump(raw,sort_keys=False))
    base=load_profile(source)
    catalog=build_asset_catalog(base)
    records=[]
    for phase in ('natural','forced'):
        variants={name:configured(base,name,phase=='forced') for name in TREATMENTS}
        target=root/'paired'/phase;target.mkdir(parents=True)
        planner=ScenePlanner(variants['pristine'],catalog)
        with execution_scope(plan_execution(base)):
            synthesis=BackgroundSynthesizer(catalog,base.recipes)
            for slot in range(-args.warmups,args.samples):
                for attempt in range(base.profile.run.max_candidate_attempts):
                    try:
                        plan=planner.plan(slot,attempt)
                        bg=synthesis.synthesize(plan.recipe_id,plan.canvas_size,np.random.default_rng(derive_seed(base.profile.run.seed,slot,attempt,'background-synthesis')))
                        SceneRenderer(variants['pristine']).render(plan,bg)
                        break
                    except SceneRejected:
                        continue
                else: raise RuntimeError('No valid paired base fixture')
                reference=None
                # Rotate treatment order within phase/slot too; all use the same synthesized background.
                offset=(slot+args.warmups)%len(TREATMENTS)
                for name in TREATMENTS[offset:]+TREATMENTS[:offset]:
                    variant=variants[name]
                    current=ScenePlanner(variant,catalog).plan(slot,attempt)
                    assert [i.signature() for i in current.instances]==[i.signature() for i in plan.instances]
                    assert np.array_equal(current.scene_to_output,plan.scene_to_output)
                    started=perf_counter()
                    try:
                        rendered=SceneRenderer(variant).render(current,bg)
                    except SceneRejected as exc:
                        if name!='occlusion': raise
                        if slot>=0: records.append({'phase':phase,'slot':slot,'treatment':name,'status':'rejected','rejections':list(exc.rejected_instances),'render_seconds':perf_counter()-started})
                        continue
                    elapsed=perf_counter()-started
                    identity=mask_identity(rendered)
                    if name!='occlusion':
                        if reference is None: reference=identity
                        assert reference==identity,'Appearance treatment changed masks/boxes'
                    if slot<0: continue
                    if slot<6:
                        Image.fromarray(rendered.image).save(target/f'{slot:03d}-{name}.jpg',quality=92)
                    records.append({'phase':phase,'slot':slot,'treatment':name,'status':'accepted','render_seconds':elapsed,
                        'mask_identity':identity,'geometry':current.geometry_signature(),'exclusive_ns':rendered.exclusive_timings_ns,
                        'instances':len(rendered.annotations),'visible_support':[a.visible_support_fraction for a in rendered.annotations],
                        'scene_effects':rendered.scene_effects,'rejections':list(rendered.rejected_instances),
                        'effects':[{'id':t['id'],'applied':t['applied'],'stage':t['stage']} for t in rendered.effect_traces]})
                print(f'paired {phase} slot {slot}',flush=True)
    result={'schema_version':1,'kind':'paired-planar-surfaces','samples':args.samples,'warmups':args.warmups,'dimensions':[512,512],
            'source_generation_identity':generation_identity(base,catalog),'software':software_identity(),'source':source_identity(),
            'appearance_masks_boxes_equal':True,'records':records,
            'limits':['Synthetic engineering fixtures, uncalibrated settings; no detector transfer measurement.','Occlusion comparisons intentionally permit annotation changes.','Render-only timings exclude shared synthesis, output and QA.']}
    (root/'paired.json').write_text(json.dumps(result,indent=2))
    montage(root,'natural',TREATMENTS,range(min(4,args.samples)))
    montage(root,'forced',TREATMENTS,range(min(4,args.samples)))


def production(args):
    root=args.output_dir
    if (root/'production').exists(): raise ValueError('Production destination must be fresh')
    destination=root/'production';destination.mkdir(parents=True)
    base=yaml.safe_load(args.config.read_text())
    configs={}
    for name,preset,scene in [('heavy','realistic-heavy',{}),('camera','camera-minimal',{}),
                              ('surface','surface-camera',{'lighting':{}}),
                              ('occlusion','surface-camera',{'lighting':{},'occlusion':{}})]:
        raw={**base,'appearance':{'preset':'builtin:appearance/'+preset}}
        raw['inline']={**raw.get('inline',{}),'scene':scene,'output':{'image_size':[1280,1280]},
                       'execution':{'workers':1,'native_threads':1,'max_in_flight':2,'decoded_cache_mb':0},'reporting':{'qa_samples':4}}
        path=destination/(name+'.yaml');path.write_text(yaml.safe_dump(raw,sort_keys=False));configs[name]=path
    names=list(configs);records=[]
    for repeat in range(args.repeats):
        for name in names[repeat%len(names):]+names[:repeat%len(names)]:
            cell=destination/f'{repeat:02d}-{name}'
            command=[sys.executable,'-m','dataset_generator_m1','benchmark','--production','--config',str(configs[name]),
                     '--samples',str(args.samples),'--warmup',str(args.warmups),'--repeats','1','--output-dir',str(cell),'--output-format','json']
            (root/'progress.json').write_text(json.dumps({'stage':'production','repeat':repeat,'treatment':name,'completed':len(records)}))
            started=perf_counter();system=[]
            with (destination/f'{repeat:02d}-{name}.log').open('w') as log:
                process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':'src','PYTHONDONTWRITEBYTECODE':'1'})
                while True:
                    memory,swap=psutil.virtual_memory(),psutil.swap_memory()
                    system.append({'elapsed':perf_counter()-started,'available_memory_bytes':memory.available,'swap_used_bytes':swap.used,'swap_in_bytes':swap.sin,'swap_out_bytes':swap.sout,'cpu_percent':psutil.cpu_percent(None)})
                    try: code=process.wait(timeout=2);break
                    except subprocess.TimeoutExpired: pass
            (destination/f'{repeat:02d}-{name}-system.json').write_text(json.dumps(system))
            if code: raise RuntimeError(f'Production cell {repeat}/{name} failed; inspect log')
            result=json.loads((cell/'benchmark.json').read_text());row=result['records'][0]
            if result['status']!='complete' or row['accepted']!=args.samples: raise RuntimeError('Incomplete production cell')
            records.append({**row,'treatment':name,'repeat':repeat,'software':result['software'],'command_seconds':perf_counter()-started,
                            'system_min_available_bytes':min(s['available_memory_bytes'] for s in system),
                            'system_max_swap_bytes':max(s['swap_used_bytes'] for s in system),'source':source_identity()})
            (root/'production.json').write_text(json.dumps({'samples':args.samples,'warmups':args.warmups,'repeats':args.repeats,'records':records},indent=2))
            print(f'production {repeat+1}/{args.repeats} {name}: {row["throughput"]:.3f} accepted/s',flush=True)
    for name in names:
        assert len({r['content_signature'] for r in records if r['treatment']==name})==1
    assert len({r['content_signature'] for r in records if r['treatment']!='occlusion'})==1
    (root/'progress.json').write_text(json.dumps({'stage':'complete','cells':len(records)}))


def report(args):
    root=args.output_dir
    pair=json.loads((root/'paired.json').read_text());prod=json.loads((root/'production.json').read_text()) if (root/'production.json').exists() else None
    summaries=[]
    for phase in ('natural','forced'):
        for name in TREATMENTS:
            rows=[r for r in pair['records'] if r['phase']==phase and r['treatment']==name]
            accepted=[r for r in rows if r['status']=='accepted']
            activations=Counter(t['id'] for r in accepted for t in r['effects'] if t['applied'])
            summaries.append({'phase':phase,'treatment':name,'fixtures':len(rows),'accepted':len(accepted),
                'median_render_ms':median(r['render_seconds']*1000 for r in rows),'activated_effect_calls':dict(activations),
                'lighting_applied':sum(bool((r['scene_effects'].get('lighting') or {}).get('applied')) for r in accepted),
                'occlusion_applied':sum(r['scene_effects']['occlusion']['applied'] for r in accepted),
                'target_support_min':min((v for r in accepted for v in r['visible_support']),default=None),
                'rejections':dict(Counter(rj['reason'] for r in rows for rj in r.get('rejections',[])))})
    production_summary=[]
    if prod:
        for name in ('heavy','camera','surface','occlusion'):
            rows=[r for r in prod['records'] if r['treatment']==name]
            rates=[r['throughput'] for r in rows]
            production_summary.append({'treatment':name,'repeats':len(rows),'accepted_per_repeat':prod['samples'],
                'throughput_median':median(rates),'throughput_range':[min(rates),max(rates)],
                'attempts':[r['attempts'] for r in rows], 'peak_rss_bytes':max(r['resource_peaks']['rss_bytes'] for r in rows),
                'median_stage_total_seconds':{k:median(r['stage_work'].get(k,{}).get('total_ns',0)/1e9 for r in rows) for k in rows[0]['stage_work']}})
    result={'schema_version':1,'kind':'planar-surface-study','samples':pair['samples'],'warmups':pair['warmups'],'software':pair['software'],
            'source_generation_identity':pair['source_generation_identity'],'source':pair.get('source'),'appearance_masks_boxes_equal':True,
            'paired':summaries,'production':production_summary,'warnings':pair['limits']+['One host; repeated content and rotating order reduce confounding, not cross-machine evidence.','Production reports accepted throughput, including retries/masks/writes/QA; inclusive stages must not be summed with their nested render stages.']}
    images=[('natural-paired.jpg','Natural activation: pristine / light / wear / capture / surface / occlusion'),('forced-paired.jpg','Forced engineering coverage: stronger effects, not calibration')]
    write_report(root,result,'Planar surface attribution and production cost',images=images)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['paired','production','report'])
    parser.add_argument('--config',type=Path,default=Path('examples/configs/landing-pad_minimal.yaml'))
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--warmups',type=int,default=2)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.samples<1 or args.warmups<0 or args.repeats<1: raise ValueError('Invalid study counts')
    {'paired':paired,'production':production,'report':report}[args.stage](args)

if __name__=='__main__': main()
