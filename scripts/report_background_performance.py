"""Build an offline performance report from completed, exact-equivalence studies.

Requires matplotlib for authoring only. Run after timing has finished; never beside a benchmark.
Raw pools stay ignored. The output is compact, sanitized evidence suitable for deliberate promotion.
"""
import argparse
from collections import defaultdict
import html
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw


def read(path):
    return json.loads(path.read_text())


def span(values):
    return {'median': median(values), 'min': min(values), 'max': max(values)}


def groups(study):
    grouped = defaultdict(list)
    for row in study['records']:
        grouped[row['variant']].append(row)
    return {name: {
        'accepted_per_second': span([r['throughput'] for r in rows]),
        'rss_gib': span([r['resource_peaks']['rss_bytes']/2**30 for r in rows]),
        'command_seconds': span([r['command_seconds'] for r in rows]),
        'active_seconds': span([r['active_seconds'] for r in rows]),
        'generation_identity': rows[0]['generation_identity'],
        'execution': {k: rows[0]['execution'][k] for k in ['workers', 'native_threads', 'max_in_flight', 'cache_bytes_per_worker']},
        'repetitions': [{k: r[k] for k in ['repeat', 'accepted', 'attempts', 'throughput', 'active_seconds', 'wall_seconds',
            'command_seconds', 'resource_peaks', 'source', 'minimum_available_memory_bytes', 'maximum_swap_used_bytes',
            'swap_in_delta_bytes', 'swap_out_delta_bytes', 'content_signature', 'pixel_signature', 'stage_work']}
            | ({'cache_observed':r['cache_observed']} if 'cache_observed' in r else {}) for r in rows],
    } for name, rows in grouped.items()}


def errorbars(ax, data, names, metric, positions, color, label):
    middle = [data[n][metric]['median'] for n in names]
    errors = [[m-data[n][metric]['min'] for n,m in zip(names,middle)],
              [data[n][metric]['max']-m for n,m in zip(names,middle)]]
    ax.bar(positions, middle, yerr=errors, capsize=4, width=.34, color=color, label=label)
    for x,y,name in zip(positions,middle,names):
        ax.text(x,data[name][metric]['max']+.025,f'{y:.3f}' if metric=='accepted_per_second' else f'{y:.2f}',ha='center',fontsize=9)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study_root',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--allocation-json',type=Path,required=True)
    args=parser.parse_args();root=args.study_root;out=args.output_dir
    if out.exists():raise ValueError('Choose a fresh report directory')
    controls=read(root/'controls-full/summary.json')
    production=read(root/'implementation-production/summary.json')
    recipes=read(root/'implementation-full/summary.json')
    streaming=read(root/'streamed-multiband-full/summary.json')
    screen=read(root/'optimized-controls-short/summary.json')
    for study in [controls,production,recipes,streaming,screen]:
        if study['status']!='complete':raise ValueError('All studies must be complete')
    for study in [controls,production]:
        if (study['samples'],study['warmups'],study['repeats'])!=(20,2,3):raise ValueError('This retained report requires the reviewed 20/2/3 protocol')
    for study in [recipes,streaming]:
        if (study['samples_per_recipe'],study['warmups_per_recipe'],study['canvas_size'])!=(20,2,[2560,2560]):raise ValueError('Unexpected recipe protocol')
    software=production['records'][0]['software']
    for study in [controls,production,screen]:
        for row in study['records']:
            if row['source']['dirty'] or row['software']!=software:raise ValueError('Require clean checkouts and matching software')
    if recipes['software']!=software or streaming['software']!=software:raise ValueError('Recipe software differs')
    for study in [controls,production,screen]:
        if not study['exact_encoded_images_equal'] or not study['geometry_annotation_masks_equal']:
            raise ValueError('Equivalence not established')
    for study in [recipes,streaming]:
        if not study['all_pixels_qa_lineage_parameters_rng_equal']:raise ValueError('Recipe equivalence not established')
    cg,pg=groups(controls),groups(production)
    # The original control study predates summary aggregation. Recover observed
    # accepted-sample counters from its raw pools using the same high-water rule.
    control_order=list(dict.fromkeys(r['variant'] for r in controls['records']))
    if control_order!=['threads-one','threads-four','threads-default','cache-256','workers-two']:raise ValueError('Unexpected control labels')
    for name,group in cg.items():
        for row in group['repetitions']:
            pool=root/'controls-full'/f'{row["repeat"]:02d}-{control_order.index(name):02d}'/'00-configured'
            counters={}
            for line in (pool/'samples.jsonl').read_text().splitlines():
                execution=json.loads(line).get('execution',{});pid=execution.get('worker_pid',0)
                stats=execution.get('decoded_cache',{});previous=counters.get(pid,{})
                counters[pid]={key:max(previous.get(key,0),stats.get(key,0)) for key in ['hits','misses','retained_bytes']}
            row['cache_observed']={key:sum(v[key] for v in counters.values()) for key in ['hits','misses','retained_bytes']}
    policies=list(dict.fromkeys(r['variant'].split(':',1)[1] for r in production['records']))
    if policies!=['one-worker-one-thread','one-worker-24-threads','two-workers-one-thread']:raise ValueError('Unexpected selected policy labels')
    gains={}
    for policy in policies:
        before={r['repeat']:r for r in production['records'] if r['variant']=='baseline:'+policy}
        after={r['repeat']:r for r in production['records'] if r['variant']=='current:'+policy}
        gains[policy]=span([100*(after[i]['throughput']/before[i]['throughput']-1) for i in before])
    summary={'schema_version':1,'kind':'background-performance-round-two','software':production['records'][0]['software'],
        'method':{'output_pixels':[1280,1280],'canvas_pixels':[2560,2560],'foreground':'landing-pad',
            'appearance':'realistic-heavy','background_weights':{'direct':.45,'palette':.20,'mask_multiband':.25,'displaced':.10},
            'production_samples':20,'warmups':2,'repetitions':3,'qa_samples':4,'range':'observed minimum/maximum, not confidence intervals',
            'content_repeated':True,'host_logical_cpus':24,'defaults_changed':False},
        'equivalence':{'encoded_images':True,'geometry_annotation_masks':True,'recipe_pixels_qa_lineage_parameters_rng':True},
        'controls':cg,'production':pg,'paired_throughput_change_percent':gains,
        'recipes_before_streaming':recipes,'streamed_multiband':streaming,
        'allocation_probe':read(args.allocation_json),
        'queue_thread_screen':{'samples':screen['samples'],'warmups':screen['warmups'],'repeats':screen['repeats'],
            'low_sample':True,'groups':groups(screen)},
        'limits':['One host; no default or hardware-class promotion.',
            'Repeated deterministic content measures execution variation, not additional independent scenes.',
            'Sampled RSS is an observed process-tree maximum, not guaranteed peak or a hard RAM bound.',
            'Traced kernel allocations exclude input arrays and are distinct from process RSS.',
            'Cache counters are observed high-water values on accepted samples, not exhaustive accounting.',
            'No real-model quality measurement; exact equality is confined to this software environment.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f6f7f5','axes.facecolor':'#f6f7f5'})
    blue='#286a86';orange='#d38634'
    names=list(cg);x=np.arange(len(names))
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,metric,title in zip(axes,['accepted_per_second','rss_gib'],['Accepted images / second','Per-run sampled peak RSS (GiB)']):
        errorbars(ax,cg,names,metric,x,blue,'Original implementation')
        ax.set_xticks(x,['1 worker\n1 thread','1 worker\n4 threads','1 worker\n24 threads','1 worker\n256 MiB cache','2 workers\n1 thread each'])
        ax.set_title(title);ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Existing controls — 3 × 20 accepted images + 2 warmups per cell\nBars: medians; whiskers: observed ranges on one host; defaults unchanged',fontsize=13)
    fig.savefig(out/'execution-controls.png',dpi=150);plt.close(fig)
    x=np.arange(len(policies));labels=['1 worker\n1 native thread','1 worker\n24 native threads','2 workers\n1 native thread each']
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,metric,title in zip(axes,['accepted_per_second','rss_gib'],['Accepted images / second','Per-run sampled peak RSS (GiB)']):
        for prefix,offset,color,label in [('baseline',-.18,blue,'Original'),('current',.18,orange,'Optimized')]:
            errorbars(ax,pg,[prefix+':'+p for p in policies],metric,x+offset,color,label)
        ax.set_xticks(x,labels);ax.set_title(title);ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2);ax.legend()
    fig.suptitle('Same encoded pixels and exact annotations — interleaved production A/B\n3 × 20 accepted + 2 warmups per cell; bars: medians; whiskers: observed ranges',fontsize=13)
    fig.savefig(out/'production-comparison.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained',gridspec_kw={'width_ratios':[2,1]})
    keys=list(recipes['recipes']);x=np.arange(len(keys))
    for name,offset,color,label in [('baseline',-.18,blue,'Original'),('current',.18,orange,'Copies + DAG lifetime')]:
        y=[recipes['recipes'][k][name]['median_seconds'] for k in keys]
        axes[0].bar(x+offset,y,.34,color=color,label=label)
    axes[0].set_xticks(x,['Direct','Palette','Mask multiband','Displaced']);axes[0].set_ylabel('Median synthesis seconds');axes[0].legend();axes[0].grid(axis='y',alpha=.2)
    y=[streaming['recipes']['mask_multiband'][n]['median_seconds'] for n in ['baseline','current']]
    axes[1].bar([0,1],y,color=[blue,orange]);axes[1].set_xticks([0,1],['Before streaming','After streaming']);axes[1].set_title('Separate incremental pair');axes[1].set_ylabel('Median multiband recipe seconds');axes[1].grid(axis='y',alpha=.2)
    fig.suptitle('Recipe microbenchmarks — 20 paired fixtures + 2 warmups, native thread = 1\nExact pixels / QA / lineage / sampled parameters / RNG state; large smoothing cost remains',fontsize=13)
    fig.savefig(out/'recipe-comparison.png',dpi=150);plt.close(fig)
    # Nonoverlapping top-level worker/coordinator work. Nested render spans are excluded.
    stages=['background_synthesis','scene_render','mask_encode','mask_polygonization','mask_write','qa_render','image_encode_write','scene_plan']
    names=['baseline:'+policies[0],'current:'+policies[0]]
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained');left=np.zeros(2)
    for stage in stages:
        values=[median([r['stage_work'].get(stage,{}).get('total_ns',0)/r['accepted']/1e9 for r in pg[n]['repetitions']]) for n in names]
        ax.barh([0,1],values,left=left,label=stage.replace('_',' '));left+=values
    ax.set_yticks([0,1],['Original','Optimized']);ax.set_xlabel('Median measured stage work seconds / accepted image');ax.legend(bbox_to_anchor=(1,1),loc='upper left',fontsize=9)
    ax.set_title('Work attribution, one worker / one native thread\nTop-level stage work excludes preparation/warmup; it is not full command wall time')
    fig.savefig(out/'stage-work.png',dpi=150);plt.close(fig)
    pools=[root/'implementation-production'/f'00-{i:02d}'/'00-configured' for i in [0,1]]
    samples=[[json.loads(line) for line in (p/'samples.jsonl').read_text().splitlines()] for p in pools]
    sheet=Image.new('RGB',(1024,4*295+38),'#f6f7f5');draw=ImageDraw.Draw(sheet)
    draw.text((12,10),'Original / optimized: fixed first four accepted scenes; encoded bytes identical',fill='#20323d')
    for i in range(4):
        for j in range(2):
            row=samples[j][i];path=pools[j]/row['image_path']
            if j and path.read_bytes()!=(pools[0]/samples[0][i]['image_path']).read_bytes():raise ValueError('Sheet pair differs')
            image=Image.open(path).convert('RGB')
            if image.size!=(1280,1280):raise ValueError('Unexpected production image dimensions')
            image.thumbnail((500,260))
            sheet.paste(image,(j*512+(512-image.width)//2,38+i*295))
            draw.text((j*512+12,38+i*295+265),f'{"Original" if j==0 else "Optimized"} · slot {row["slot"]} · {row["background"]["recipe_id"]}',fill='#20323d')
    sheet.save(out/'identical-scenes.jpg',quality=90)
    def table(data):
        rows=[]
        for name,values in data.items():
            t=values['accepted_per_second'];m=values['rss_gib'];c=values['command_seconds']
            rows.append(f'<tr><td>{html.escape(name)}</td><td>{t["median"]:.3f} ({t["min"]:.3f}–{t["max"]:.3f})</td><td>{m["max"]:.2f}</td><td>{c["median"]:.1f}</td></tr>')
        return '<table><tr><th>Case</th><th>Accepted/s: median (range)</th><th>Max sampled RSS GiB</th><th>Median full command seconds</th></tr>'+''.join(rows)+'</table>'
    content='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Background performance — round two</title><style>body{max-width:1300px;margin:auto;padding:28px;font:16px/1.55 system-ui;background:#f6f7f5;color:#20323d}h1,h2{line-height:1.2}img{max-width:100%;height:auto}figure{margin:28px 0}table{border-collapse:collapse;display:block;overflow:auto}th,td{padding:9px 15px;text-align:left;border-bottom:1px solid #bbc6cc}a{color:#166085}.note{padding:16px;background:#e5ece8}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Background performance: exact output, less redundant work</h1><p class="note">One host; unchanged defaults. This study measures computational cost and exact equivalence in the recorded software environment. It supplies no real-model accuracy or photographic-realism result.</p><p>Production: landing pads, realistic-heavy appearance, standard background mixture, 1280² output on a 2560² canvas. Each cell has 2 warmups and 20 measured accepted images; 3 rotating-order repetitions reuse deterministic content. Generation throughput excludes preparation and warmup. Full command time includes them. Range bars are observed minimum/maximum, not confidence intervals.</p><h2>What changed</h2><p>Read-only float32 consumers avoid redundant array copies. Background DAG values are released after their final use, including asset-constraint references. Multiband blending streams the same per-level arithmetic into reconstruction. Identical full/visible masks reuse one polygon projection. Generation semantics, RNG progression and defaults stay unchanged; cost observations use a new implementation identity.</p><h2>Existing controls</h2>'''
    content+=table(cg)+'<figure><img src="execution-controls.png" alt="Existing execution settings throughput and sampled memory"><figcaption>Native threading helps on this host. The 256 MiB decoded cache did not improve this workload; it is not a generic performance recommendation.</figcaption></figure><h2>Interleaved implementation comparison</h2>'+table(pg)
    allocation=summary['allocation_probe']['records']
    before_bytes=allocation['baseline']['peak_traced_bytes'];after_bytes=allocation['current']['peak_traced_bytes']
    allocation_note=f'<p>Separate 1024² float32 kernel probe: {before_bytes/2**20:.2f}→{after_bytes/2**20:.2f} MiB peak traced temporaries ({100*(1-after_bytes/before_bytes):.1f}% lower). Inputs were allocated before tracing. This includes all kernel changes since the original baseline and is not process RSS.</p>'
    content+='<figure><img src="production-comparison.png" alt="Original versus optimized production throughput and sampled memory"></figure><figure><img src="stage-work.png" alt="Top level work attribution"></figure><h2>Recipe isolation</h2><figure><img src="recipe-comparison.png" alt="Paired background recipe synthesis durations"></figure><p>Copies and value lifetime help direct/palette/displaced work; multiband streaming chiefly reduces workspace. Large Gaussian smoothing remains dominant. Changing smoothing resolution, precision, kernel approximation or recipe mixture would change fidelity or distribution and requires a new planning decision.</p>'+allocation_note+'<h2>Visual equivalence</h2><figure><img src="identical-scenes.jpg" alt="First four accepted scenes before and after optimization"><figcaption>Exact encoded bytes match across all production cases; these four fixed-prefix examples illustrate the preserved outputs.</figcaption></figure><h2>Evidence and limits</h2><p><a href="summary.json">Compact measurements, per-repeat stage/resource evidence, source hashes and software versions</a></p><ul>'
    content+=''.join('<li>'+html.escape(limit)+'</li>' for limit in summary['limits'])
    content+='</ul><p>Memory availability and swap activity are retained per cell. Existing swap use does not establish a cause for timing differences. Resource planning estimates are advisory and can underpredict observed RSS. Larger queues had unstable results in a 5-image screen and were not promoted. Two-worker runs measure summed worker work alongside coordinator wall time; do not equate them.</p></html>'
    (out/'index.html').write_text(content)
    print(json.dumps({'output':str(out),'paired_change_percent':gains},indent=2))


if __name__=='__main__':main()
