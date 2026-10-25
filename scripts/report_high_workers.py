"""Build the completed/aborted high-worker evidence and validate phase RAM estimates."""
import argparse
from collections import defaultdict
import hashlib
import html
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.memory_planning import recipe_peak_bytes, source_shapes
from dataset_generator_m1.models import ExecutionConfig


def read(path):return json.loads(path.read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study_root',type=Path)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--previous-report',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();root=args.study_root;out=args.output_dir
    if out.exists():raise ValueError('Fresh report output required')
    full=read(root/'six-full/summary.json')
    if full['status']!='complete' or (full['samples'],full['warmups'],full['repeats'])!=(48,2,3):raise ValueError('Require complete48/2/3 protocol')
    if not full['exact_encoded_images_equal'] or not full['geometry_annotation_masks_equal']:raise ValueError('Missing equivalence')
    value=load_profile(args.config);groups=defaultdict(list)
    for row in full['records']:
        if row['source']['dirty'] or row['inspection']!='valid' or row['accepted']!=48:raise ValueError('Invalid production evidence')
        groups[row['variant']].append(row)
    def forecast(workers,threads,window):
        policy=ExecutionConfig(workers=workers,native_threads=threads,max_in_flight=window,ram_budget_mb=12288)
        return plan_execution(value.model_copy(update={'profile':value.profile.model_copy(update={'execution':policy})}))
    complete={}
    for name,rows in groups.items():
        if len(rows)!=3:raise ValueError('Missing repetitions')
        policy=rows[0]['execution'];plan=forecast(policy['workers'],policy['native_threads'],policy['max_in_flight'])
        rate=[r['throughput'] for r in rows]
        observed=max(max(r['resource_peaks']['rss_bytes'],r['command_resource_observed']['peak_rss_bytes']) for r in rows)
        if plan.estimated_peak_bytes<observed:raise ValueError('Phase estimate below completed observed RSS')
        complete[name]={'workers':policy['workers'],'native_threads':policy['native_threads'],
            'throughput':{'median':median(rate),'min':min(rate),'max':max(rate)},
            'maximum_observed_rss_bytes':observed,
            'maximum_observed_pss_bytes':max(r['command_resource_observed']['peak_pss_bytes'] for r in rows),
            'phase_estimate_bytes':plan.estimated_peak_bytes,'memory_components':plan.memory_estimate,
            'repetitions':[{key:r[key] for key in ['repeat','source','software','generation_identity','pixel_signature','content_signature',
                'accepted','attempts','throughput','active_seconds','command_seconds','resource_peaks','command_resource_observed',
                'guard_limits','minimum_available_memory_bytes','maximum_swap_used_bytes','swap_in_delta_bytes','swap_out_delta_bytes']} for r in rows]}
    raw_abort=read(root/'ramp-twelve/abort.json');system=read(root/'ramp-twelve/00-00-system.json')
    if raw_abort['status']!='guard-aborted' or raw_abort['reason']!='available host memory floor':raise ValueError('Unexpected capacity decision')
    aborted={**raw_abort,'workers':12,'native_threads':1,
        'minimum_available_memory_bytes':min(s['available_memory_bytes'] for s in system),
        'peak_observed_pss_bytes':max((s['pss_bytes'] for s in system if s['pss_complete']),default=None),
        'swap_out_delta_bytes':system[-1]['swap_out_bytes']-system[0]['swap_out_bytes'],
        'throughput':None,'metric_limit':'Partial sampled peaks are lower bounds, not completed-pool maxima.'}
    earlier=read(args.previous_report);comparisons={}
    for name,g in earlier['groups'].items():
        plan=forecast(g['workers'],g['native_threads'],g['max_in_flight'])
        observed=max(g['maximum_generation_sampled_rss_bytes'],g['maximum_command_sampled_rss_bytes'])
        comparisons[name]={'workers':g['workers'],'native_threads':g['native_threads'],
            'observed_rss_bytes':observed,'v2_estimate_bytes':g['revised_estimated_peak_bytes'],
            'v3_estimate_bytes':plan.estimated_peak_bytes,'v2_ratio':g['revised_estimated_peak_bytes']/observed,
            'v3_ratio':plan.estimated_peak_bytes/observed}
        if plan.estimated_peak_bytes<observed:raise ValueError('Phase estimate below retained observed RSS')
    allocations=read(root/'allocations/summary.json');by_recipe=defaultdict(list)
    for row in allocations['records']:by_recipe[row['recipe']].append(row['peak_traced_bytes'])
    cw,ch=allocations['canvas_size'];shapes=source_shapes(value)
    traced={}
    for name,peaks in by_recipe.items():
        predicted=recipe_peak_bytes(value.recipes.recipes[name],cw*ch,shapes)
        traced[name]={'max_traced_bytes':max(peaks),'predicted_array_peak_bytes':predicted,'ratio':predicted/max(peaks)}
        # Tracing includes small Python metadata absent from the pixel formula;
        # compare within 0.5%, then apply runtime/headroom in the RSS forecast.
        if predicted<max(peaks)*.995:raise ValueError('Operation allowance under traced arrays')
    summary={'schema_version':1,'kind':'high-worker-capacity-and-phase-memory','complete':complete,'aborted':aborted,
        'skipped':{'twelve2':'First 12-worker case reached the available-memory floor.',
            'sixteen1and2':'Escalation stopped after 12 workers failed the headroom condition.',
            'twentyfour1and2':'User condition requires safe lower-count evidence; 12-worker ramp already stopped.'},
        'protocol':{'samples':48,'warmups':2,'repeats':3,'output_pixels':[1280,1280],'appearance':'realistic-heavy',
            'background_mix':'standard','foreground':'landing-pad','qa_samples':4,'cache_mib':0,
            'guard_rss_gib':12,'guard_pss_gib':3.5,'minimum_available_gib':2.5,'max_swap_out_mib':16,
            'poll_interval_seconds':.1,'pss_interval_seconds':1},
        'earlier_rss_comparisons':comparisons,'array_allocation_validation':traced,
        'allocation_probe':allocations,
        'model_sources':{name:hashlib.sha256((Path('src/dataset_generator_m1')/name).read_bytes()).hexdigest() for name in ['memory_planning.py','execution.py']},
        'limits':['One host; ranges are observed extrema, not confidence intervals.',
            'Repeated scenes measure execution variation;48/2 protocol differs from the historical24/2 workload prefix.',
            'RSS planning estimates include shared pages repeatedly; PSS/USS are independent physical/private-memory observations.',
            'Partial abort measurements cannot establish throughput or a completed peak.',
            'Memory guards are sampled, not hard OS limits. No 16/24-worker completion claim is made.']}
    out.mkdir(parents=True);(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f6f7f5','axes.facecolor':'#f6f7f5'})
    names=list(complete);x=np.arange(len(names));rates=[complete[n]['throughput']['median'] for n in names]
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    err=[[r-complete[n]['throughput']['min'] for n,r in zip(names,rates)],
         [complete[n]['throughput']['max']-r for n,r in zip(names,rates)]]
    axes[0].bar(x,rates,yerr=err,capsize=5,color='#286a86');axes[0].set_xticks(x,['6 workers ×1 thread','6 workers ×2 threads'])
    axes[0].set_ylabel('Accepted images / second');axes[0].set_title('Completed: 3 × 48 accepted + 2 warmups')
    labels=['6×1','6×2','12×1\npartial abort'];xx=np.arange(3)
    for offset,key,color,label in [(-.18,'maximum_observed_rss_bytes','#286a86','Summed RSS'),(.18,'maximum_observed_pss_bytes','#d38634','Proportional memory')]:
        values=[complete[n][key]/2**30 for n in names]
        values.append(aborted['peak_observed_rss_bytes' if key.endswith('rss_bytes') else 'peak_observed_pss_bytes']/2**30)
        bars=axes[1].bar(xx+offset,values,.34,color=color,label=label);bars[-1].set_hatch('//')
    axes[1].set_xticks(xx,labels);axes[1].set_ylabel('GiB: independent sampled peaks');axes[1].legend()
    for ax in axes:ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
    fig.suptitle('High-worker capacity — 12 workers reached the 2.5 GiB free-memory floor\n16 and 24 workers skipped; partial memory bars are lower bounds',fontsize=13)
    fig.savefig(out/'capacity.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,5),layout='constrained');names=list(comparisons);x=np.arange(len(names))
    for offset,key,color,label in [(-.25,'observed_rss_bytes','#286a86','Observed whole-command RSS'),
        (0,'v2_estimate_bytes','#c39a68','Previous v2'),(.25,'v3_estimate_bytes','#478e73','Phase/lifetime v3')]:
        ax.bar(x+offset,[comparisons[n][key]/2**30 for n in names],.24,label=label,color=color)
    ax.set_xticks(x,[f'{comparisons[n]["workers"]}×{comparisons[n]["native_threads"]}' for n in names]);ax.set_ylabel('GiB');ax.legend();ax.grid(axis='y',alpha=.2)
    ax.set_title('Same retained workloads: remove expired buffers and exclusive-phase sums\nRuntime reserve stays 256 MiB per process; explicit buffers +20% headroom remain')
    fig.savefig(out/'estimator.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained');names=list(traced);x=np.arange(len(names))
    ax.bar(x-.18,[traced[n]['max_traced_bytes']/2**20 for n in names],.34,label='Traced maximum, 3 fixtures',color='#286a86')
    ax.bar(x+.18,[traced[n]['predicted_array_peak_bytes']/2**20 for n in names],.34,label='Phase/lifetime array allowance',color='#478e73')
    ax.set_xticks(x,names);ax.set_ylabel('MiB, array allocations only');ax.legend();ax.grid(axis='y',alpha=.2)
    ax.set_title('Independent array-lifetime validation — 2560² canvas\nInterpreter/import baseline and global RAM headroom are separate')
    fig.savefig(out/'arrays.png',dpi=150);plt.close(fig)
    content='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>High-worker capacity and corrected RAM estimates</title><style>body{max-width:1250px;margin:auto;padding:28px;font:16px/1.55 system-ui;background:#f6f7f5;color:#20323d}img{max-width:100%}a{color:#166085}li{margin:8px 0}</style><h1>More workers: capacity first, then throughput</h1><p>The 12-worker ramp reached the 2.5 GiB available-memory floor after about 7 seconds. Its isolated coordinator/workers were stopped. 12×2,16 and 24 are skipped because the lower-count headroom condition failed. No completed 12-worker throughput or complete peak is inferred.</p><p>Completed six-worker cases preserve exact encoded images, masks and annotation signatures. Three rotating-order repetitions use 48 accepted 1280² heavy pad scenes (+2 warmups), standard background mixture, cache 0 and four QA samples. Repeated deterministic scenes measure execution variation. Whole-command memory includes preparation/warmup, while generation throughput excludes them.</p><p><img src="capacity.png" alt="Completed six-worker throughput and partial 12-worker capacity stop"></p><h2>Fixing excessive estimation</h2><p>The prior estimator counted expired arrays and added synthesis, foreground rendering and mask-processing peaks together. The replacement uses the renderer's release schedule, operation scratch, precision propagation and maximum worker phase. Each source's decode/cover sizes stay correlated; extreme foreground rotation/resize remains accounted for. Runtime stays 256 MiB per process. Result/cache/native reserves and 20% headroom are explicit.</p><p><img src="estimator.png" alt="Retained observed RSS compared with previous and corrected RAM estimates"></p><p><img src="arrays.png" alt="Independent traced recipe arrays compared with operation allowances"></p><p>Predictions are RSS planning upper estimates. Summed RSS repeats shared pages; Linux PSS counts proportional physical memory, and USS counts private pages. These are different metrics, with different sampling rates. The available-memory guard checks the host at 0.1-second intervals; detailed PSS/USS is sampled once per second. A sampled guard is not an OS hard cap.</p><ul>'''
    content+=''.join('<li>'+html.escape(v)+'</li>' for v in summary['limits'])+'</ul><p><a href="summary.json">Per-repeat measurements, abort, skipped decisions, allocation evidence and source hashes</a></p></html>'
    (out/'index.html').write_text(content)
    print(json.dumps({'complete':{n:g['throughput'] for n,g in complete.items()},'comparisons':comparisons,'trace_validation':traced},indent=2))


if __name__=='__main__':main()
