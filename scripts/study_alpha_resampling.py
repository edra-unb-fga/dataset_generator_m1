"""Paired production-renderer study; shared synthesis is timed once, not duplicated."""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter_ns

import cv2
import numpy as np
from PIL import Image, ImageDraw

from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.backgrounds import BackgroundSynthesizer
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.generator import _annotation_record
from dataset_generator_m1.identities import software_identity
from dataset_generator_m1.imaging import resize_rgba, rotate_rgba, warp_rgba
from dataset_generator_m1.scene import ScenePlanner, SceneRenderer, SceneRejected, derive_seed


def signature(rendered):
    arrays = rendered.full_coverages + rendered.visible_coverages
    return {'annotations': [_annotation_record(a) for a in rendered.annotations],
            'masks': [hashlib.sha256(m.tobytes()).hexdigest() for m in arrays],
            'rejected': rendered.rejected_instances}


def edge_fixture(root):
    a = np.zeros((64, 64, 4), np.uint8)
    a[12:52, 12:52] = [240, 20, 20, 255]
    b = a.copy(); b[b[:, :, 3] == 0, :3] = [0, 255, 0]
    results=[]
    for corrected in (False, True):
        pair=[]
        for source in (a,b):
            rgba=rotate_rgba(source,17.3,'square',premultiplied=corrected)
            rgba=resize_rgba(rgba,37,premultiplied=corrected)
            rgba=warp_rgba(rgba,np.array([[1.,.02,7.],[-.02,1.,7.],[.0001,.0002,1.]]),(64,64),premultiplied=corrected)
            alpha=rgba[:,:,3:4]/255
            pair.append((rgba[:,:,:3]*alpha+160*(1-alpha)).astype(np.uint8))
        results.append(pair)
    canvas=Image.new('RGB',(768,410),'white');draw=ImageDraw.Draw(canvas)
    for row,pair in enumerate(results):
        for col,value in enumerate(pair):
            canvas.paste(Image.fromarray(value).resize((192,192),Image.Resampling.NEAREST),(col*384,row*205+13))
            draw.text((col*384+194,row*205+30),('premultiplied' if row else 'legacy')+'\nhidden '+('green' if col else 'black'),fill='black')
    canvas.save(root/'edge-fixture.png')
    return [{'mode': mode,'changed_pixels':int(np.count_nonzero(np.any(p[0]!=p[1],axis=2))),
             'max_channel_delta':int(np.abs(p[0].astype(int)-p[1].astype(int)).max())}
            for mode,p in zip(('legacy','premultiplied'),results)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--warmups',type=int,default=2)
    args=parser.parse_args()
    if args.output_dir.exists() or args.samples<1 or args.warmups<0:raise ValueError('Fresh output and positive samples required')
    root=args.output_dir;root.mkdir(parents=True)
    cv2.setNumThreads(1)
    report={'software':software_identity(),'samples':args.samples,'warmups':args.warmups,
            'edge_fixture':edge_fixture(root),'families':{},'cost_scope':'paired renderer; synthesis shared, encode/write excluded'}
    for family in ('landing','manometro','landing-pad'):
        resolved=load_profile(f'examples/configs/{family}_minimal.yaml')
        catalog=build_asset_catalog(resolved)
        planner=ScenePlanner(resolved,catalog);synth=BackgroundSynthesizer(catalog,resolved.recipes)
        corrected=resolved.model_copy(update={'profile':resolved.profile.model_copy(update={
            'scene':resolved.profile.scene.model_copy(update={'foreground_resampling':'premultiplied'})})})
        renderers={'legacy':SceneRenderer(resolved),'premultiplied':SceneRenderer(corrected)}
        rows=[];thumbs=[]
        for index in range(args.samples+args.warmups):
            for attempt in range(resolved.profile.run.max_candidate_attempts):
                plan=planner.plan(index,attempt)
                start=perf_counter_ns()
                try:
                    background=synth.synthesize(plan.recipe_id,plan.canvas_size,np.random.default_rng(derive_seed(resolved.profile.run.seed,index,attempt,"background-synthesis")))
                    synthesis=perf_counter_ns()-start
                    pairs={};times={}
                    order=list(renderers)
                    if index%2:order.reverse()
                    for mode in order:
                        start=perf_counter_ns();pairs[mode]=renderers[mode].render(plan,background);times[mode]=perf_counter_ns()-start
                    assert signature(pairs['legacy'])==signature(pairs['premultiplied'])
                    break
                except SceneRejected:
                    continue
            else:raise RuntimeError('No accepted paired fixture')
            if index<args.warmups:continue
            a,b=pairs['legacy'].image,pairs['premultiplied'].image
            delta=np.abs(a.astype(np.int16)-b.astype(np.int16))
            rows.append({'slot':index,'attempt':attempt,'synthesis_ns':synthesis,'render_ns':times,
                         'changed_pixels':int(np.count_nonzero(np.any(delta,axis=2))),
                         'maximum_channel_delta':int(delta.max()),'mean_absolute_delta':float(delta.mean())})
            if len(thumbs)<4:
                tile=Image.new('RGB',(640,205),'white');draw=ImageDraw.Draw(tile)
                for col,(mode,value) in enumerate((('legacy',a),('premultiplied',b))):
                    image=Image.fromarray(value);image.thumbnail((316,180))
                    tile.paste(image,(col*320,20));draw.text((col*320+4,3),mode,fill='black')
                thumbs.append(tile)
        sheet=Image.new('RGB',(640,205*len(thumbs)),'white')
        for index,tile in enumerate(thumbs):sheet.paste(tile,(0,index*205))
        sheet.save(root/f'{family}.jpg')
        report['families'][family]={'records':rows,'exact_alpha_masks_annotations':True,
            'median_render_ms':{mode:float(np.median([row['render_ns'][mode]/1e6 for row in rows])) for mode in renderers}}
        (root/'summary.json').write_text(json.dumps(report,indent=2))
        print(family,report['families'][family]['median_render_ms'],flush=True)
    sections=['<h1>Opt-in alpha resampling</h1><p>Paired production renderer, same plans/backgrounds; exact alpha, masks and annotations. Render timings exclude synthesis and output costs. No model-benefit claim.</p>', '<img src="edge-fixture.png" alt="Transparent hidden RGB diagnostic">']
    for family,value in report['families'].items():sections.extend([f'<h2>{family}</h2><p>{value["median_render_ms"]}</p>',f'<img src="{family}.jpg" alt="Paired {family} views">'])
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Alpha resampling</title>'+''.join(sections))

if __name__=='__main__':main()
