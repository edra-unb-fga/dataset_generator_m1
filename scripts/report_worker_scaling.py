"""Author offline scaling evidence after timing has completed (optional matplotlib dependency)."""
import argparse
from collections import defaultdict
import html
import hashlib
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.models import ExecutionConfig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study_root',type=Path)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();root=args.study_root;out=args.output_dir
    if out.exists():raise ValueError('Choose a fresh report directory')
    full=json.loads((root/'full/summary.json').read_text())
    ramp=json.loads((root/'ramp/summary.json').read_text())
    if full['status']!='complete' or full['samples']!=24 or full['repeats']!=3 or full['warmups']!=2:raise ValueError('Require complete 24/2/3 protocol')
    if not full['exact_encoded_images_equal'] or not full['geometry_annotation_masks_equal']:raise ValueError('Missing equivalence')
    grouped=defaultdict(list)
    for row in full['records']:
        if row['source']['dirty'] or row['inspection']!='valid' or row['accepted']!=24:raise ValueError('Invalid source or pool')
        grouped[row['variant']].append(row)
    resolved=load_profile(args.config);summary={}
    for name,rows in grouped.items():
        if len(rows)!=3:raise ValueError('Incomplete repetition group')
        policy=ExecutionConfig.model_validate(rows[0]['execution']['requested'])
        current=resolved.model_copy(update={'profile':resolved.profile.model_copy(update={'execution':policy})})
        plan=plan_execution(current)
        rate=[r['throughput'] for r in rows]
        observed=max(max(r['resource_peaks']['rss_bytes'],r['command_resource_observed']['peak_rss_bytes']) for r in rows)
        summary[name]={'workers':policy.workers,'native_threads':policy.native_threads,'max_in_flight':policy.max_in_flight,
            'throughput':{'median':median(rate),'min':min(rate),'max':max(rate)},
            'maximum_generation_sampled_rss_bytes':max(r['resource_peaks']['rss_bytes'] for r in rows),
            'maximum_command_sampled_rss_bytes':max(r['command_resource_observed']['peak_rss_bytes'] for r in rows),
            'maximum_command_observed_threads':max(r['command_resource_observed']['peak_threads'] for r in rows),
            'previous_estimated_peak_bytes':rows[0]['execution']['estimated_peak_bytes'],
            'revised_estimated_peak_bytes':plan.estimated_peak_bytes,'revised_memory_components':plan.memory_estimate,
            'revised_estimate_exceeds_observed':plan.estimated_peak_bytes>=observed,
            'repetitions':[{k:r[k] for k in ['repeat','source','software','generation_identity','pixel_signature','content_signature',
                'accepted','attempts','throughput','active_seconds','wall_seconds','command_seconds','resource_peaks',
                'command_resource_observed','guard_limits','minimum_available_memory_bytes','maximum_swap_used_bytes',
                'swap_in_delta_bytes','swap_out_delta_bytes']} for r in rows]}
    if not all(g['revised_estimate_exceeds_observed'] for g in summary.values()):raise ValueError('Revised estimate still under observed workloads')
    result={'schema_version':1,'kind':'worker-native-scaling','protocol':{'samples':24,'warmups':2,'repeats':3,
        'output_pixels':[1280,1280],'appearance':'realistic-heavy','foreground':'landing-pad','background_mix':'standard',
        'cache_mib':0,'requested_ram_budget_mib':12288,'defaults_changed':False,'same_scenes_repeated':True},
        'exact_encoded_images_equal':True,'geometry_annotation_masks_equal':True,'groups':summary,
        'estimator_sources':{name:hashlib.sha256((Path('src/dataset_generator_m1')/name).read_bytes()).hexdigest()
                             for name in ['execution.py','memory_planning.py']},
        'ramp':{'samples':ramp['samples'],'warmups':ramp['warmups'],'repeats':ramp['repeats'],'low_sample':True,
            'measurements':[{k:r[k] for k in ['variant','throughput','resource_peaks','command_resource_observed']} for r in ramp['records']]},
        'limits':['One host; ranges are observed minima/maxima, not confidence intervals.',
            'Summed process RSS repeats shared pages and sampled peaks can miss spikes.',
            'Command observations include preparation and warmup; generation telemetry does not.',
            'Native threads configure OpenCV per worker; other libraries and actual active threading differ.',
            'The revised RAM model is conservative shape accounting, not a hard RSS bound or a fitted universal predictor.']}
    out.mkdir(parents=True);(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    names=list(summary);x=np.arange(len(names));labels=[f'{summary[n]["workers"]}w × {summary[n]["native_threads"]}t' for n in names]
    plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f6f7f5','axes.facecolor':'#f6f7f5'})
    rates=[summary[n]['throughput']['median'] for n in names]
    errors=[[v-summary[n]['throughput']['min'] for n,v in zip(names,rates)],
            [summary[n]['throughput']['max']-v for n,v in zip(names,rates)]]
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    axes[0].bar(x,rates,yerr=errors,capsize=4,color='#286a86');axes[0].set_ylabel('Accepted images / second')
    axes[0].set_title('Bars: medians; whiskers: observed ranges')
    for i,(n,v) in enumerate(zip(names,rates)):axes[0].text(i,summary[n]['throughput']['max']+.02,f'{v:.3f}',ha='center')
    for offset,key,color,label in [(-.18,'maximum_generation_sampled_rss_bytes','#286a86','Generation telemetry'),
                                   (.18,'maximum_command_sampled_rss_bytes','#d38634','Whole-command watchdog')]:
        axes[1].bar(x+offset,[summary[n][key]/2**30 for n in names],.34,color=color,label=label)
    axes[1].set_ylabel('Maximum sampled process-tree RSS (GiB)');axes[1].legend()
    for ax in axes:ax.set_xticks(x,labels);ax.grid(axis='y',alpha=.2);ax.set_ylim(bottom=0)
    fig.suptitle('Worker / OpenCV thread scaling — 3 × 24 accepted + 2 warmups per cell\nIdentical encoded images and exact annotation/mask evidence; one host',fontsize=13)
    fig.savefig(out/'scaling.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
    for offset,key,color,label in [(-.25,'previous_estimated_peak_bytes','#9b9b91','Previous estimate'),
        (0,'maximum_command_sampled_rss_bytes','#286a86','Maximum command RSS observed'),
        (.25,'revised_estimated_peak_bytes','#d38634','Revised conservative estimate')]:
        ax.bar(x+offset,[summary[n][key]/2**30 for n in names],.24,color=color,label=label)
    ax.axhline(12,color='#9c4f4f',linestyle='--',label='Requested 12 GiB ceiling')
    ax.set_xticks(x,labels);ax.set_ylabel('GiB');ax.legend();ax.grid(axis='y',alpha=.2)
    ax.set_title('RAM accounting — explicit process/source/graph/queue reserves + 25% headroom\nValidation exceeds observed workloads; this is not an OS memory limit')
    fig.savefig(out/'memory-estimates.png',dpi=150);plt.close(fig)
    rows=[]
    for n,g in summary.items():
        t=g['throughput'];rows.append(f'<tr><td>{html.escape(n)}</td><td>{t["median"]:.3f} ({t["min"]:.3f}–{t["max"]:.3f})</td><td>{g["maximum_command_sampled_rss_bytes"]/2**30:.2f}</td><td>{g["revised_estimated_peak_bytes"]/2**30:.2f}</td><td>{g["maximum_command_observed_threads"]}</td></tr>')
    content='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Worker scaling and RAM accounting</title><style>body{max-width:1300px;margin:auto;padding:28px;font:16px/1.55 system-ui;background:#f6f7f5;color:#20323d}img{max-width:100%}table{border-collapse:collapse;display:block;overflow:auto}td,th{padding:10px;border-bottom:1px solid #bcc8cc;text-align:left}a{color:#166085}</style><h1>Workers, native threads and conservative RAM</h1><p>Six workers with24 OpenCV threads each is a useful oversubscription stress case. Requested threads do not establish active OS parallelism. Compare measured throughput, memory and thread observations independently. Renderer source and all encoded images/annotation/mask signatures are unchanged across treatments.</p><p>1280² heavy landing pads, standard background mix, cache disabled, four QA outputs. Three rotating-order repetitions reuse24 deterministic scenes; two warmups are in separate pools. Generation throughput includes startup for its own pool and excludes preparation/separate warmup. Whole-command observations include both. Range bars are observed ranges, not confidence intervals.</p><table><tr><th>Case</th><th>Median accepted/s (range)</th><th>Max command RSS GiB</th><th>Revised estimate GiB</th><th>Observed command thread peak</th></tr>'''
    content+=''.join(rows)+'</table><p><img src="scaling.png" alt="Worker and native thread throughput and sampled memory"></p><p><img src="memory-estimates.png" alt="Previous and revised RAM estimates against observed memory"></p><p>The watchdog used4.5 GiB summed RSS,1.5 GiB available host-memory floor,64 MiB additional host swap-out and180-second cell timeout. This lower experimental limit reflects current host availability; the requested12 GiB budget is not a hard allocation bound. New estimates are recalculated from the same policies with the revised model; they did not alter the measured renderer runs.</p><p>The planner now checks the complete estimate before choosing automatic workers and respects explicit queue capacity. Source dimension headers, cover expansion, graph/scratch storage, instance masks, processes, native reserves, serialized return buffers, caches and headroom are reported as components. Explicit worker counts still run with advisory warnings. Auto can choose fewer workers. Every revised estimate exceeds this study’s observed workloads; arbitrary effects/native libraries still prevent a universal guarantee.</p><ul>'
    content+=''.join('<li>'+html.escape(v)+'</li>' for v in result['limits'])+'</ul><p><a href="summary.json">Per-repeat measurements, identities, guard limits and estimate components</a></p></html>'
    (out/'index.html').write_text(content)
    print(json.dumps({n:{k:v for k,v in g.items() if k not in ['repetitions','revised_memory_components']} for n,g in summary.items()},indent=2))


if __name__=='__main__':main()
