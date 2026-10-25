"""Build static scientific charts and a portable offline readout from the reviewed study bundle.

Requires matplotlib only for report authoring, not generation. Run after study_planar_surfaces.py report.
"""
import argparse
from collections import Counter
import html
import json
from pathlib import Path
from statistics import median

import numpy as np
from PIL import Image, ImageDraw


def build(root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root=Path(root)
    result=json.loads((root/'summary.json').read_text())
    production=json.loads((root/'production.json').read_text())
    paired=json.loads((root/'paired.json').read_text())
    assert len(production['records'])==4*production['repeats']
    assert all(row['status']=='complete' and row['inspection']=='valid' and row['accepted']==production['samples'] for row in production['records'])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f5f5f2','axes.facecolor':'#f5f5f2'})
    names=['heavy','camera','surface','occlusion'];colors=['#7d8194','#2f6f9e','#31856e','#c1833b']
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    for i,name in enumerate(names):
        rates=[r['throughput'] for r in production['records'] if r['treatment']==name]
        center=median(rates)
        axes[0].bar(i,center,color=colors[i],width=.6)
        axes[0].errorbar(i,center,yerr=[[center-min(rates)],[max(rates)-center]],color='#243744',capsize=5,fmt='none')
        axes[0].scatter([i]*len(rates),rates,color='#243744',s=18,zorder=3)
        axes[0].text(i,max(rates)+.02,f'{center:.3f}',ha='center',fontsize=10)
    axes[0].set(xticks=range(4),xticklabels=names,ylabel='Accepted images / second',title='Production: median, range and each repetition',ylim=(0,None))
    labels=['background_synthesis','scene_render','mask_polygonization','qa_render','image_encode_write','mask_encode','mask_write']
    bottom=np.zeros(4)
    palette=['#9aa5bc','#31856e','#c1833b','#7e5b8d','#c9b896','#87997c','#6d8791']
    for label,color in zip(labels,palette):
        values=[median(r['stage_work'].get(label,{}).get('total_ns',0)/1e9/r['accepted'] for r in production['records'] if r['treatment']==name) for name in names]
        axes[1].bar(range(4),values,bottom=bottom,color=color,label=label.replace('_',' '));bottom+=values
    axes[1].set(xticks=range(4),xticklabels=names,ylabel='Serial stage work / accepted image (s)',title='Selected non-overlapping stages; not wall time')
    axes[1].legend(fontsize=8)
    fig.savefig(root/'production-cost.png',dpi=160);fig.savefig(root/'production-cost.svg');plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.5),layout='constrained')
    treatments=['pristine','light-only','wear-only','capture-only','surface','occlusion'];x=np.arange(len(treatments))
    for offset,phase,color in [(-.18,'natural','#31856e'),(.18,'forced','#c1833b')]:
        rows=[next(r for r in result['paired'] if r['phase']==phase and r['treatment']==name) for name in treatments]
        ax.bar(x+offset,[r['median_render_ms'] for r in rows],width=.34,color=color,label=phase)
    ax.set(xticks=x,xticklabels=treatments,ylabel='Median render time (ms)',title='512² paired attribution: shared background, unchanged appearance masks')
    ax.legend();fig.savefig(root/'paired-cost.png',dpi=160);fig.savefig(root/'paired-cost.svg');plt.close(fig)
    activation=[]
    for phase in ('natural','forced'):
        for name in ['pristine','light-only','wear-only','capture-only','surface','occlusion']:
            rows=[r for r in paired['records'] if r['phase']==phase and r['treatment']==name and r['status']=='accepted']
            eligible=Counter(t['id'] for r in rows for t in r['effects'])
            applied=Counter(t['id'] for r in rows for t in r['effects'] if t['applied'])
            activation.append({'phase':phase,'treatment':name,'accepted_scene_denominator':len(rows),
                'effects':{key:{'eligible_calls':value,'applied_calls':applied[key]} for key,value in eligible.items()}})
    result['activation_coverage']=activation
    result['activation_limits']='Accepted-fixture traces count effect calls, including foreground attempts later rejected for clipping; calls do not imply visible contribution. Rejected occlusion fixtures lack traces.'
    evidence=[];crops=[]
    for row in production['records']:
        pool=root/'production'/f"{row['repeat']:02d}-{row['treatment']}"/'00-configured'
        samples=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines()]
        rejected=[json.loads(line) for line in (pool/'rejections.jsonl').read_text().splitlines()]
        counts=Counter(a['class_name'] for sample in samples for a in sample['annotations'])
        support=[a['visible_support_fraction'] for sample in samples for a in sample['annotations']]
        qa=[item for sample in samples for item in sample['segmentation_quality']['instances']]
        evidence.append({'repeat':row['repeat'],'treatment':row['treatment'],'class_instances':dict(counts),
            'minimum_visible_support':min(support,default=None),'median_visible_support':median(support) if support else None,
            'candidate_rejections':dict(Counter(r['reason'] for r in rejected if r.get('record_type')!='object-attempt')),
            'accepted_sample_object_rejections':dict(Counter(r['reason'] for sample in samples for r in sample['rejected_instances'])),
            'rejected_candidate_object_rejections':dict(Counter(r['reason'] for candidate in rejected for r in candidate.get('object_rejections',[]))),
            'minimum_visible_polygon_iou':min((i['semantics']['visible']['iou'] for i in qa),default=None),
            'visible_polygon_warning_instances':sum(bool(i['semantics']['visible']['warnings']) for i in qa)})
        if row['repeat']==0:
            # Same selected sample across appearance arms; include border/background context.
            sample=samples[0];image=Image.open(pool/sample['image_path'])
            annotation=next((a for a in sample['annotations'] if a['bbox'][0]>100 and a['bbox'][1]>100),sample['annotations'][0])
            x1,y1,x2,y2=annotation['bbox'];pad=24
            crop=image.crop((max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad),min(image.height,y2+pad)))
            crop.thumbnail((360,360));crops.append((row['treatment'],crop))
    sheet=Image.new('RGB',(360*len(crops),400),'#f5f5f2');draw=ImageDraw.Draw(sheet)
    for i,(name,crop) in enumerate(crops): sheet.paste(crop,(360*i,30));draw.text((360*i+8,8),f'{name}: actual output crop',(20,40,50))
    sheet.save(root/'production-crops.jpg',quality=92)
    recipes=[]
    for name in names:
        selected=next(r for r in production['records'] if r['treatment']==name)
        pool=root/'production'/f"{selected['repeat']:02d}-{name}"/'00-configured'
        samples=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines()]
        for recipe in sorted({sample['background']['recipe_id'] for sample in samples}):
            values=[sample['stage_timings_ns']['background_synthesis']/1e9 for sample in samples if sample['background']['recipe_id']==recipe]
            recipes.append({'treatment':name,'recipe':recipe,'accepted_scene_calls':len(values),'median_seconds':median(values),'maximum_seconds':max(values)})
    result['accepted_scene_background_recipes']=recipes
    result['production_annotation_evidence']=evidence
    result['validation']={'production_cells':len(production['records']),'all_complete_and_valid':True,
        'same_treatment_content_stable':all(len({r['content_signature'] for r in production['records'] if r['treatment']==name})==1 for name in names),
        'appearance_production_content_equal':len({r['content_signature'] for r in production['records'] if r['treatment']!='occlusion'})==1}
    assert all(result['validation'][k] for k in ('all_complete_and_valid','same_treatment_content_stable','appearance_production_content_equal'))
    result['production_environment']={'minimum_available_memory_bytes':min(r['system_min_available_bytes'] for r in production['records']),
        'maximum_swap_used_bytes':max(r['system_max_swap_bytes'] for r in production['records']),
        'sources':[r['source'] for r in production['records']]}
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    def table(headers,rows):
        cell=lambda values,tag:''.join(f'<{tag}>{html.escape(str(v))}</{tag}>' for v in values)
        return '<table><thead><tr>'+cell(headers,'th')+'</tr></thead><tbody>'+''.join('<tr>'+cell(r,'td')+'</tr>' for r in rows)+'</tbody></table>'
    prod_table=table(['Profile','Median images/s','Range (3 runs)','Attempts / 20 accepted','Peak RSS GiB'],[
        [r['treatment'],f"{r['throughput_median']:.3f}",' – '.join(f'{v:.3f}' for v in r['throughput_range']),r['attempts'],f"{r['peak_rss_bytes']/1024**3:.2f}"] for r in result['production']])
    pair_table=table(['Activation','Treatment','Accepted / fixtures','Render median ms','Lighting scenes','Occlusion scenes','Min visible support'],[
        [r['phase'],r['treatment'],f"{r['accepted']} / {r['fixtures']}",f"{r['median_render_ms']:.1f}",r['lighting_applied'],r['occlusion_applied'],f"{r['target_support_min']:.3f}" if r['target_support_min'] is not None else 'unavailable'] for r in result['paired']])
    camera=next(r for r in result['production'] if r['treatment']=='camera');surface=next(r for r in result['production'] if r['treatment']=='surface')
    narrative=f'''<h2>What the evidence supports</h2><p>Shared illumination applies one coherent low-frequency field. Local wear adds target-specific color damage without moving mask edges. At 1280², surface throughput is {surface['throughput_median']/camera['throughput_median']:.2f}× the restrained-camera median on this host. These are opt-in engineering configurations; unchanged defaults and no real-model accuracy claim.</p><p>The blade/debris fixtures provide controlled coverage and exact label tests. They remain visibly procedural. Activation totals use accepted paired fixtures; rejected occlusion fixtures lack effect traces. Natural activation is sparse; forced examples exaggerate coverage and severity deliberately. Real vegetation, height, contact shadows, wrinkles and surface reflectance remain unresolved. Full versus visible mask policy matters more than visual sharpness for trustworthy labels.</p><p>Next performance work should follow the measured stages below: background synthesis and source raster work, then polygon/QA/output costs where they dominate. Test caching only against representative asset reuse and bounded memory; profile reuse, source resolution and background-mixture changes separately because they can change diversity or pixels.</p>'''
    content='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Planar realism — evidence and limits</title><style>body{max-width:1450px;margin:auto;padding:28px;font:16px/1.55 system-ui;background:#f5f5f2;color:#20323d}h1,h2{line-height:1.2}img{max-width:100%;height:auto}figure{margin:28px 0}table{border-collapse:collapse;display:block;overflow:auto}td,th{padding:9px 15px;text-align:left;border-bottom:1px solid #b9c8cb}th{background:#e4eae4}a{color:#12638b}.note{padding:16px;background:#e8ece3}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Planar surfaces: quality controls and generation cost</h1><p class="note">Synthetic acceptance only. No real labels, model predictions or physical calibration were supplied. Image attractiveness, oracle AP≈1 and consistent masks do not establish deployment accuracy.</p><p>Paired screens: 20 measured +2 warmup fixtures per treatment, natural and forced, 512². Production: 3 rotating-order repetitions ×20 accepted +2 warmups per cell, 1280², one worker/native thread, cache disabled, standard background mixture, four QA samples. Repeated content is an execution check, not 60 independent scenes. Measured generation throughput excludes preparation and warmup; full command durations are retained in production.json.</p>'''
    content+=narrative+'<h2>Accepted production throughput</h2>'+prod_table+'<figure><img src="production-cost.png" alt="Throughput repetitions and selected production stage costs"><figcaption>Range bars show observed minima/maxima, not confidence intervals. Stages are serial work and include retries; selected stage sums are not wall-clock time.</figcaption></figure><h2>Paired attribution and activation</h2>'+pair_table+'<figure><img src="paired-cost.png" alt="Natural and forced median render times"><figcaption>Shared background synthesis, pool writing and QA are excluded from render-only attribution.</figcaption></figure>'
    for name,caption in [('natural-paired.jpg','Natural activation: pristine, light-only, wear-only, capture-only, combined surface, occlusion.'),('forced-paired.jpg','Forced engineering coverage. Occluders change labels; appearance-only masks and boxes remain identical.'),('production-crops.jpg','Actual production target crops; context retained, thumbnail sizes vary with projected target.')]:
        content+=f'<figure><img src="{name}" alt="{html.escape(caption)}"><figcaption>{caption}</figcaption></figure>'
    content+='<h2>Provenance, evidence and future work</h2><p><a href="summary.json">Compact measurements and validation</a> · <a href="paired.json">Paired fixture records</a> · <a href="production.json">Production repetitions and stage work</a> · <a href="production-cost.svg">Vector production chart</a> · <a href="paired-cost.svg">Vector paired chart</a></p><p>Every production pool passed inspection; same-treatment content is stable across repetitions, and appearance-only production content matches. Polygon IoU and topology warnings are recorded separately from exact pool masks. Host RAM/swap observations accompany results; no machine-independent timing gate or profile promotion follows.</p><p>Future evidence: permitted real development/holdout captures, external predictions and training provenance (#59); measured target size/camera/capture conditions (#61); PBR/raised geometry (#62/#63); and an optional matched BlenderProc study with equal dataset-size/time budgets (#64). Full raw pools remain ignored.</p></html>'
    (root/'index.html').write_text(content)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);args=parser.parse_args();build(args.root)
