"""Author compact portable-tuning evidence after measurement (optional Matplotlib)."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--screen', required=True, type=Path)
    parser.add_argument('--recommendation', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    study, screen, choice = read(args.study), read(args.screen), read(args.recommendation)
    if args.output_dir.exists() or study['status'] != 'complete' or screen['status'] != 'complete':
        raise ValueError('Complete studies and a fresh report directory are required')
    if hashlib.sha256(json.dumps(study, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != choice['study_sha256']:
        raise ValueError('Recommendation does not belong to this study')
    groups = defaultdict(list)
    for row in study['records']:
        groups[row['variant']].append(row)
    results = []
    retained = []
    for name, rows in groups.items():
        rates = [r['throughput'] for r in rows]
        results.append({'variant': name, 'workers': rows[0]['execution']['workers'],
            'native_threads': rows[0]['execution']['native_threads'],
            'throughput': {'median': median(rates), 'min': min(rates), 'max': max(rates)},
            'peak_rss_bytes': max(max(r['command_resource_observed']['peak_rss_bytes'],r['resource_peaks']['rss_bytes']) for r in rows),
            'peak_pss_bytes': max((r['command_resource_observed']['peak_pss_bytes'] for r in rows
                                   if r['command_resource_observed']['peak_pss_bytes'] is not None), default=None),
            'minimum_available_bytes': min(r['minimum_available_memory_bytes'] for r in rows),
            'background_mean_seconds': median(r['stage_work']['background_synthesis']['mean_ns']/1e9 for r in rows)})
        for row in rows:
            retained.append({key:row[key] for key in ['variant','repeat','source','software','tuning_context','generation_identity',
                'pixel_signature','content_signature','accepted','attempts','throughput','active_seconds','command_seconds',
                'initial_available_memory_bytes','minimum_available_memory_bytes','swap_out_delta_bytes','guard_limits','command_resource_observed']}
                | {'execution': {key:row['execution'][key] for key in ['workers','native_threads','max_in_flight','cache_bytes_per_worker']}})
    screening = [{key:row[key] for key in ['variant','throughput','source','software','generation_identity','pixel_signature','content_signature']}
                 | {'workers':row['execution']['workers'], 'native_threads':row['execution']['native_threads']} for row in screen['records']]
    summary = {'schema_version':1,'kind':'portable-execution-tuning-evidence',
        'protocol':{key:study[key] for key in ['samples','warmups','repeats','tuning_context','exact_encoded_images_equal','geometry_annotation_masks_equal']},
        'screen_protocol':{key:screen[key] for key in ['samples','warmups','repeats']},
        'screen':screening,'groups':results,'repetitions':retained,'recommendation':choice,
        'authoring_sources':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
            ['src/dataset_generator_m1/execution_tuning.py','scripts/study_execution_controls.py']},
        'limits':['One hardware class; not a generic fastest-worker formula.',
            'Three repeated deterministic prefixes measure execution variation, not independent scene diversity.',
            'Observed ranges are not confidence intervals. Near-best selection uses an explicit resource preference.',
            'Sampled RSS, PSS and host availability are distinct metrics, not OS hard limits.']}
    out = args.output_dir; out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f6f7f5','axes.facecolor':'#f6f7f5'})
    x=np.arange(len(results)); rates=[r['throughput']['median'] for r in results]
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    colours=['#478e73' if r['variant']==choice['selected']['variant'] else '#286a86' for r in results]
    errors=[[v-r['throughput']['min'] for r,v in zip(results,rates)],[r['throughput']['max']-v for r,v in zip(results,rates)]]
    axes[0].bar(x,rates,color=colours,yerr=errors,capsize=5)
    axes[0].axhline(choice['fastest']['throughput']['median']*(1-choice['method']['near_best_tolerance_percent']/100),ls='--',color='#b07f35',label='Near-best threshold')
    axes[0].set_ylabel('Accepted images / second');axes[0].set_title('Median and observed range; green = selected');axes[0].legend()
    axes[1].bar(x-.18,[r['peak_rss_bytes']/2**30 for r in results],.34,color='#286a86',label='Summed RSS')
    pss=[r['peak_pss_bytes']/2**30 if r['peak_pss_bytes'] is not None else np.nan for r in results]
    axes[1].bar(x+.18,pss,.34,color='#d38634',label='Proportional memory (where supported)')
    axes[1].set_ylabel('GiB: independent sampled peaks');axes[1].legend();axes[1].set_title('Memory cost of extra workers')
    for ax in axes:
        ax.set_xticks(x,[f"{r['workers']} × {r['native_threads']}" for r in results]);ax.set_xlabel('Workers × OpenCV threads');ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
    fig.suptitle(f"Local execution tuning: {study['repeats']} repeats × {study['samples']} accepted images + {study['warmups']} separate warmups",fontsize=13)
    fig.savefig(out/'confirmation.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    labels=[f"{r['workers']} × {r['native_threads']}" for r in screening]
    ax.bar(np.arange(len(screening)),[r['throughput'] for r in screening],color=['#286a86' if r['native_threads']==1 else '#d38634' for r in screening])
    ax.set_xticks(np.arange(len(screening)),labels);ax.set_ylabel('Accepted images / second');ax.set_xlabel('Workers × OpenCV threads');ax.grid(axis='y',alpha=.2)
    ax.set_title(f"Screen only: {screen['samples']} images, {screen['repeats']} repetition(s) — eliminate poor candidates, then confirm")
    fig.savefig(out/'screen.png',dpi=150);plt.close(fig)
    print(json.dumps({'selected':choice['selected'],'groups':results},indent=2))


if __name__=='__main__':
    main()
