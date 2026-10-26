"""Author compact standalone pilot evidence from ignored raw outputs (optional Matplotlib)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
from PIL import Image, ImageDraw

from dataset_generator_m1.blender_pilot import completed_outputs, load_study, atomic_json


def sheet(items, target, columns=3, size=400):
    height=size+42
    canvas=Image.new('RGB',(columns*size,((len(items)+columns-1)//columns)*height),'#eeeeee')
    draw=ImageDraw.Draw(canvas)
    for index,(label,file) in enumerate(items):
        x=index%columns*size;y=index//columns*height
        with Image.open(file) as image:
            image=image.convert('RGB');image.thumbnail((size,size))
            canvas.paste(image,(x+(size-image.width)//2,y+32+(size-image.height)//2))
        draw.text((x+8,y+8),label,fill='#172b3a')
    canvas.save(target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--pristine',type=Path,required=True)
    parser.add_argument('--surface',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    study=load_study(args.study);rows=completed_outputs(args.study,study)
    accepted={j['id']:(j,p,r) for j,p,r in rows if r['status']=='accepted'}
    baseline=accepted['000-base-fast'];comparisons=[]
    with np.load(baseline[1]/'masks.npz') as masks:reference_visible=masks['visible'].copy();reference_full=masks['full'].copy()
    base=np.asarray(Image.open(baseline[1]/'rgb.png').convert('RGB')).astype(float)
    foreground=reference_visible.any(axis=0)
    for name,(job,path,result) in accepted.items():
        if job['scene_index']!=0 or job['quality']!='fast' or job['case']!='ordinary':continue
        reference_name='000-'+(job['treatment'].get('paired_reference') or 'base')+'-fast'
        reference=accepted[reference_name]
        base=np.asarray(Image.open(reference[1]/'rgb.png').convert('RGB')).astype(float)
        with np.load(reference[1]/'masks.npz') as masks:
            reference_visible=masks['visible'].copy();reference_full=masks['full'].copy()
        foreground=reference_visible.any(axis=0)
        image=np.asarray(Image.open(path/'rgb.png').convert('RGB')).astype(float)
        with np.load(path/'masks.npz') as masks:
            equal=bool(np.array_equal(reference_visible,masks['visible']) and np.array_equal(reference_full,masks['full']))
        difference=np.abs(image-base).mean(axis=2)
        comparisons.append({'job':name,'reference_job':reference_name,'masks_equal_reference':equal,
            'foreground_mean_absolute_rgb_difference':float(difference[foreground].mean()),
            'background_mean_absolute_rgb_difference':float(difference[~foreground].mean()),
            'changed_rgb_pixels_fraction':float((difference>0).mean())})
    source=[];controls={};control_rows=[]
    for label,pool in [('2D pristine',args.pristine),('2D surface camera',args.surface)]:
        records=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines()]
        row=records[0];source.append((label,pool/row['image_path']));control_rows.append(records)
        result=json.loads((pool/'summary.json').read_text())
        evidence=json.loads((pool.parents[1]/'summary.json').read_text())
        controls[label]={'accepted':len(records),'warmups':evidence['warmups'],'repeats':evidence['repeats'],
            'accepted_per_second':result['throughput_images_per_second'],
            'elapsed_seconds':result['elapsed_seconds'],'source_samples_sha256':__import__('hashlib').sha256((pool/'samples.jsonl').read_bytes()).hexdigest(),
            'context':evidence['tuning_context'],'source':evidence['records'][0]['source'],
            'peak_rss_bytes':evidence['records'][0]['command_resource_observed'].get('peak_rss_bytes'),
            'native_threads':evidence['records'][0]['execution']['native_threads'],
            'workers':evidence['records'][0]['execution']['workers'],
            'command_seconds':evidence['records'][0]['command_seconds'],
            'guard_limits':evidence['records'][0]['guard_limits'],
            'minimum_available_memory_bytes':evidence['records'][0]['minimum_available_memory_bytes']}
    if len(control_rows[0])!=len(control_rows[1]):raise ValueError('2D control counts differ')
    geometry_equal=all(a['geometry_signature']==b['geometry_signature'] for a,b in zip(*control_rows))

    source.extend((name,accepted[name][1]/'rgb.png') for name in
                  ('000-base-fast','000-night-mixed-fast','000-glint-satin-fast','000-motion-fast'))
    sheet(source,args.output/'selected.png')
    paired=[(name,p/'rgb.png') for name,(j,p,r) in accepted.items() if j['scene_index']==0 and j['quality']=='fast']
    sheet(paired,args.output/'treatments.jpg',columns=4,size=320)
    qa=[];qa_dir=args.output/'.qa-overlays';qa_dir.mkdir(exist_ok=True)
    for name,(job,path,result) in accepted.items():
        if job['case']=='ordinary':continue
        rgb=np.asarray(Image.open(path/'rgb.png').convert('RGB')).copy()
        with np.load(path/'masks.npz') as masks:
            for mask in masks['visible']:
                rgb[mask]=(rgb[mask]*.75+np.array([0,255,100])*.25).astype(np.uint8)
                contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(rgb,contours,-1,(0,255,100),max(1,rgb.shape[0]//256))
        file=qa_dir/(name+'.png');Image.fromarray(rgb).save(file);qa.append((name,file))
    if qa:sheet(qa,args.output/'annotations.jpg',columns=3,size=400)
    shutil.rmtree(qa_dir)
    quality_items=[];quality_crops=[]
    crop_dir=args.output/'.quality-crops';crop_dir.mkdir(exist_ok=True)
    for index in range(study['config']['scenes']):
        for treatment in ('base','night-mixed'):
            fast=f'{index:03d}-{treatment}-fast';quality=f'{index:03d}-{treatment}-quality'
            if fast not in accepted or quality not in accepted:continue
            with np.load(accepted[fast][1]/'masks.npz') as masks:
                visible=masks['visible'];mask=visible[int(np.argmax(visible.sum(axis=(1,2))))]
            ys,xs=np.where(mask);width,height=study['config']['resolution']
            crop_size=min(400,width,height)
            x=int(np.clip((xs.min()+xs.max())/2-crop_size/2,0,width-crop_size));y=int(np.clip((ys.min()+ys.max())/2-crop_size/2,0,height-crop_size))
            quality_crops.append({'scene':index,'treatment':treatment,'crop_xywh':[x,y,crop_size,crop_size]})
            for name in (fast,quality):
                file=crop_dir/(name+'.png')
                with Image.open(accepted[name][1]/'rgb.png') as image:image.crop((x,y,x+crop_size,y+crop_size)).save(file)
                quality_items.append((name+' native crop',file))
    if quality_items:sheet(quality_items,args.output/'quality.png',columns=2,size=400)
    shutil.rmtree(crop_dir)
    for name in ('costs.png',):shutil.copy2(args.study/name,args.output/name)
    raw=json.loads((args.study/'summary.json').read_text())
    # Keep the compact evidence portable; raw input paths remain only in ignored study provenance.
    raw['reference'].pop('counts',None)
    raw['quality_crops']=quality_crops
    raw['appearance_comparisons']=comparisons
    raw['2d_controls']=controls
    raw['2d_control_geometry_equal']=geometry_equal
    raw['configuration']={key:value for key,value in study['config'].items() if key not in
                         ('reference_pool','artwork','grounds','environments')}
    raw['source_contract']={key:value for key,value in study['contract'].items() if key.endswith('sha256')}
    raw['asset_provenance']=study['contract']['assets']
    raw['resume_evidence']=json.loads((args.study/'resume-evidence.json').read_text()) if (args.study/'resume-evidence.json').exists() else None
    raw['evaluator_evidence']=json.loads((args.study/'evaluator-evidence.json').read_text()) if (args.study/'evaluator-evidence.json').exists() else None
    raw['coco']=json.loads((args.study/'coco-export.json').read_text())
    raw['yolo']=json.loads((args.study/'yolo-conversion.json').read_text())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    observations=[row for row in comparisons if row['masks_equal_reference'] and row['job']!=row['reference_job']]
    fig,ax=plt.subplots(figsize=(10,max(4,len(observations)*.32)),layout='constrained')
    y=np.arange(len(observations))
    ax.barh(y-.18,[r['foreground_mean_absolute_rgb_difference'] for r in observations],height=.35,color='#d89438',label='Inside sharp target masks')
    ax.barh(y+.18,[r['background_mean_absolute_rgb_difference'] for r in observations],height=.35,color='#476b82',label='Outside target masks')
    ax.set_yticks(y,[r['job'].replace('000-','').replace('-fast','') for r in observations]);ax.invert_yaxis()
    ax.set_xlabel('Mean absolute RGB channel difference (0–255); one paired scene')
    ax.set_title('Measured image change, not a realism or detector score')
    ax.spines[['top','right']].set_visible(False);ax.legend(loc='lower right')
    fig.savefig(args.output/'appearance-impact.png',dpi=140);plt.close(fig)
    atomic_json(args.output/'summary.json',raw)
    (args.output/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>BlenderProc pilot evidence</title>
<style>body{font:16px system-ui;max-width:1300px;margin:2em auto;padding:0 1em}img{max-width:100%}</style>
<h1>Targeted BlenderProc pilot</h1><p>Engineering evidence on one CPU host; no real-world detector benefit or physical calibration measured.
See <a href="README.md">analysis and limitations</a> and <a href="summary.json">inspectable measurements</a>.</p>
<h2>2D and selected physical views</h2><img src="selected.png" alt="Pristine and surface 2D, physical daylight, night, glint and camera motion">
<h2>Controlled treatments</h2><img src="treatments.jpg" alt="Paired material lighting camera and annotation treatments">
<h2>Geometric annotation diagnostics</h2><img src="annotations.jpg" alt="Sharp visible mask contours under clipping occlusion overlap closeup and negatives">
<h2>32 / 128 sample native crops</h2><img src="quality.png" alt="Matching native-resolution target crops at fast and quality samples on each ground">
<h2>Image change</h2><img src="appearance-impact.png" alt="RGB change inside and outside target masks for one paired scene; not a realism score">
<h2>Costs</h2><img src="costs.png" alt="Per treatment RGB and complete output costs with individual scene observations">
''')
    print(json.dumps({'accepted':raw['accepted'],'output':str(args.output)},indent=2))


if __name__=='__main__':main()
