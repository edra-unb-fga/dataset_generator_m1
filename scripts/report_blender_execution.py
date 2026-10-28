"""Author compact execution evidence and plots; no Blender runtime is required."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence-dir',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--denoising');p.add_argument('--cpu-study');a=p.parse_args()
    from dataset_generator_m1.blender_execution import load_catalog
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    root=Path(a.evidence_dir);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);data=json.loads((root/'summary.json').read_text())
    def brief(rows):
        return [{k:r[k] for k in ['repeat','variant','mean_output_seconds','mean_label_seconds','command_seconds'] if k in r} |
                {k:r[k] for k in ['images_per_second','command_images_per_second'] if k in r} |
                {'peak_rss_bytes':r['resources']['peak_rss_bytes'],'peak_gpu_memory_mib':r['resources']['sampled_peak_gpu_memory_mib']} for r in rows]
    compact={'initialization':{'rows':brief(data['initialization_summary']),'verdict':data['initialization_verdict']},
             'workers':{'rows':brief(data['workers_summary']),'verdict':data['workers_verdict']},
             'qualification_pairs':data['qualification_pairs'],'qualification_exports':data['qualification_exports'],
             'validated_outputs':data['validated_outputs'],'repeatability':[{k:v for k,v in r.items() if k!='rows'} for r in data['repeatability']],
             'paired_rgb_mean_mae':statistics.mean(r['rgb_mae'] for r in data['initialization_comparison']),
             'paired_rgb_worst_mae':max(r['rgb_mae'] for r in data['initialization_comparison']),
             'profiles':load_catalog().model_dump(mode='json'),
             'source_fingerprints':{name:json.loads((root/name/'study.json').read_text())['contract']['harness_sources'] for name in ['qualification-1280','sealed-smoke']},
             'hardware':data['qualification_execution']['qualification-1280']['selection']['hardware'],
             'qualification_runs':data['qualification_runs'],
             'study_design':{name:{'matrix':json.loads((root/name/'matrix.json').read_text()),
                                  'driver_sha256':hashlib.sha256((root/name/'driver-source.py').read_bytes()).hexdigest()}
                             for name in ['initialization','workers']}}
    archive=root.parent/'runtime-evidence.tar.gz'
    if archive.exists():
        with archive.open('rb') as stream:
            compact['evidence_archive_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    if a.denoising:
        original=json.loads(Path(a.denoising).read_text());compact['denoising']={key:original[key] for key in ['cases','quality_against_raw512']}
    if a.cpu_study:
        cpu=Path(a.cpu_study);compact['cpu_qualification']={'exports':json.loads((cpu/'coco-export.json').read_text()),'execution':json.loads((cpu/'execution.json').read_text())['selection']['profile']}
    (out/'compact.json').write_text(json.dumps(compact,indent=2)+'\n')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
    for ax,rows,names,key,title in [(axes[0],data['initialization_summary'],['stock','guarded'],'images_per_second','Initialization: measured complete output'),(axes[1],data['workers_summary'],['one-process','two-processes'],'command_images_per_second','Guarded workers: common command wall')]:
        values=[[r[key] for r in rows if r['variant']==name] for name in names]
        ax.bar(names,[statistics.median(v) for v in values],color=['#718398','#126f83'])
        for i,v in enumerate(values):ax.scatter([i]*len(v),v,color='#192e41',s=25,zorder=3)
        ax.set_title(title);ax.set_ylabel('Accepted images / second');ax.set_ylim(0,max(max(v) for v in values)*1.25)
        for i,v in enumerate(values):ax.text(i,max(v)+.018,f'{statistics.median(v):.3f}',ha='center')
        ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Colab T4 · 640² · 3 alternating-order repetitions · 2 warmups + 20 measured scenes',fontsize=13)
    fig.savefig(out/'execution.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(11,7.4),layout='constrained')
    for col,(job,label) in enumerate([('000-base-fast','Day / marking'),('000-night-fast','Night'),('000-dof-fast','Depth of field')]):
        for row,group in enumerate(['qualification-stock','qualification-1280']):
            image=Image.open(root/group/'scenes'/job/'rgb.png').convert('RGB')
            axes[row,col].imshow(image);axes[row,col].set_xticks([]);axes[row,col].set_yticks([])
            if row==0:axes[row,col].set_title(label)
        axes[0,0].set_ylabel('Stock initialization');axes[1,0].set_ylabel('Guarded initialization')
    fig.suptitle('1280² qualification: same scene/seed/settings; sharp masks match exactly',fontsize=13)
    fig.savefig(out/'qualification.png',dpi=130);plt.close(fig)
    init=data['initialization_verdict'];workers=data['workers_verdict'];gain=init['median_gain'];wg=workers['median_gain']
    lines=['# BlenderProc execution consolidation','','Date: 2026-10-26. One Linux CPU host and a Colab Tesla T4 allocation. This is optional research-harness evidence, not a core-generator GPU backend or a real-model accuracy result.','',
           '## Saved policies and portable pipeline','',
           'The [harness guide](../../../experiments/blenderproc/README.md) documents hardware probing, saved JSON policies, explicit overrides, immutable execution identities, shared resource guards and verified source/input bundles. The standalone bootstrap uses uv and BlenderProc; no Git clone is required. CPU and generic-GPU auto profiles retain stock initialization. Only the tested Colab T4 auto profiles enable guarded initialization.','',
           '| Automatic profile | Device / denoiser | Workers | CPU threads | Initialization |','|---|---|---:|---|---|']
    for profile in compact['profiles']['profiles']:
        if not profile['automatic']:continue
        s=profile['settings'];threads=f"available, capped at {s['thread_cap']}" if s['threads']=='available' else str(s['threads'])
        lines.append(f"| {profile['id']} | {s['device']} / {s['denoiser']} | {s['workers']} | {threads} | {s['renderer_initialization']} |")
    lines+=['',
      'The small T4 rule requires the Colab environment, two available CPUs, at least 12 GiB reported VRAM and at most 409600 output pixels. Larger outputs use one worker. Unknown GPU hardware uses a conservative capability fallback; lack of advertised GPU OIDN support selects CPU or rejects an explicitly requested incompatible GPU profile. These defaults are operational choices, not established optima for all hardware. Resolution/samples/materials/camera stay explicit in the study config.','',
      '## Native GPU denoising findings','',
      'The earlier fixed-fixture probe compared one warmup + two measured images with native GPU OIDN against CPU compositor OIDN. At 640²: 11.74 → 3.97 s/image (2.95× throughput); at 1280²: 36.91 → 7.74 s/image (4.77×). A native CPU OIDN control retained the slow behavior. Two/six CPU-thread controls differed little; raw 128 was closer to the approximate raw 512 reference but slower than GPU-OIDN 32. Those are low-sample, one-fixture findings; do not multiply their speedup by the later study’s different-workload gain. OptiX denoising failed in an earlier runtime probe; native GPU OIDN is the working consolidated route.','',
      '## Renderer initialization quick win','',
      f"The pinned adapter avoids assignments of already-active engine/render settings. Three alternating-order stock/guarded pairs each used two warmups and 20 measured ordinary scenes at 640², cycling the prepared reference support and three PBR grounds. Complete measured-output throughput improved by **{gain*100:.1f}% median**, with paired gains from {min(init['paired_throughput_gains'])*100:.1f}% to {max(init['paired_throughput_gains'])*100:.1f}%. All {init['comparisons']} paired full/visible mask arrays match exactly.",'',
      '![Execution study](execution.png)','',
      'Typical label cost fell from about 2.07 s to 0.40 s. The original profile identified repeated Cycles reset/free work; no geometry/annotation algorithm or full-mask semantics were weakened. Stock initialization remains available for comparison. CPU prototypes showed a small benefit and ordinary RGB variability, so CPU auto behavior was not changed.','',
      f"After that change, two one-thread processes improved aggregate common-command throughput by **{wg*100:.1f}% median** over one two-thread process ({min(workers['paired_throughput_gains'])*100:.1f}–{max(workers['paired_throughput_gains'])*100:.1f}% over three alternating pairs). This denominator includes startup and warmup outputs in both arms. The initialization study instead divides measured accepted outputs by their summed complete-output seconds. Per-process rates are never summed. All {workers['comparisons']} worker-comparison masks also match exactly.",'',
      '## RGB repeatability and broader qualification','',
      f"GPU RGB is not byte-identical even under unchanged repeated settings. The paired initialization mean absolute difference averaged {compact['paired_rgb_mean_mae']:.4f} intensity levels out of 255; the worst image mean was {compact['paired_rgb_worst_mae']:.4f}. Unchanged stock/guarded repeat statistics are retained in compact.json. This is not an exact-pixel optimization claim or proof of distributional equivalence. Scene settings/seeds, acceptance and exact geometric masks are the strict checks. Selected visual pairs show no gross marking/shadow/blur change, but real-image/model usefulness remains unmeasured.",'',
      f"The final automatic 1280/640 policies and a matched 1280 stock control each completed 13 cases: daytime, night, DOF, camera motion, distortion, haze, quality sampling and negative/clipped/occluded/hidden/overlap/closeup diagnostics. All {len(data['qualification_pairs'])} stock/guarded qualification masks match exactly. Each export contains 13 images and 36 visible instances. The final local CPU policy also completed the same 13-case contract at 256². A clean final source-bundle smoke verifies preparation, automatic selection and export after the identity-compatibility fix.",'',
      'The mixed 13-case 1280² qualification took 121.68 s with stock initialization and 96.74 s with guarded initialization (about 26% higher command throughput). This includes camera/lighting diagnostics, quality sampling and extra warm renders; it is a one-pair qualification, not another repeated speed estimate. The final 640² auto-policy qualification took 28.98 s. These cases show why the ordinary-scene 2.05× gain should not be generalized to every workload.','',
      '![Broader qualification](qualification.png)','',
      f"All {data['validated_outputs']} archived GPU outputs had RGB/NPZ hashes verified before retrieval. No RAM/swap/time guard fired. Sampled memory is not an instantaneous peak; summed RSS counts shared pages. Raw evidence retains actual driver, Blender/Python/NumPy versions, per-image settings, source identities and resource timelines. The compact evidence copy keeps all mask/result records and selected benchmark RGB; it is not a resumable pool copy. The temporary T4 allocation was terminated after retrieval.",'',
      '## Reproduction and remaining scope','',
      'Use scripts/study_blender_execution.py with the saved renderer-initialization.json or guarded-workers.json matrices under experiments/blenderproc/benchmarks. The matrix records variants, initialization mode, repetitions, warmups, dimensions and metric. The driver archives its exact source/matrix digests; compact.json retains study-source fingerprints and calculated results. Examples and the harness guide show CPU/GPU/raw-reference choices and bundle execution.','',
      'This round consolidates execution and its measured quick win. The next planning session still owns richer/calibrated materials, lighting/surface integration, representative camera/scene distributions and eventual real-image/detector validation. Additional GPU classes and native Windows/macOS rendering remain unqualified. #28/#64 are not closed by this engineering evidence.','']
    (out/'README.md').write_text('\n'.join(lines))
    print(json.dumps({'output':str(out),'initialization_gain':gain,'worker_gain':wg,'validated_outputs':data['validated_outputs']}))


if __name__=='__main__':main()
