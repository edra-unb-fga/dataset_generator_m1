"""Standalone scientific figures from the guarded paired scheduler study."""
import argparse
import json
from pathlib import Path
import statistics


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--heavy',type=Path,required=True);p.add_argument('--light',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();root=args.output_dir;root.mkdir(parents=True,exist_ok=True)
    studies={name:json.loads((path/'summary.json').read_text()) for name,path in [('heavy',args.heavy),('light',args.light)]}
    results={}
    for name,study in studies.items():
        assert study['status']=='complete' and study['exact_encoded_images_equal'] and study['geometry_annotation_masks_equal']
        arms={}
        for label in ('baseline','current'):
            rows=[r for r in study['records'] if r['implementation']==label]
            arms[label]={'median_accepted_per_second':statistics.median(r['throughput'] for r in rows),
                'rates':[r['throughput'] for r in rows],
                'peak_rss_gib':max(r['command_resource_observed']['peak_rss_bytes'] for r in rows)/2**30,
                'rss_gib':[r['command_resource_observed']['peak_rss_bytes']/2**30 for r in rows],
                'minimum_available_gib':min(r['minimum_available_memory_bytes'] for r in rows)/2**30,
                'swap_out_mib':sum(r['swap_out_delta_bytes'] for r in rows)/2**20,
                'source':rows[0]['source'],'samples':study['samples'],'repeats':study['repeats'],
                'guard_limits':rows[0]['guard_limits']}
        gain=arms['current']['median_accepted_per_second']/arms['baseline']['median_accepted_per_second']-1
        memory=arms['current']['peak_rss_gib']/arms['baseline']['peak_rss_gib']-1
        results[name]={'arms':arms,'throughput_gain_fraction':gain,'peak_rss_change_fraction':memory,
                       'gate_pass':gain>=(.05 if name=='heavy' else -.05) and memory<=.15}
    assert all(r['gate_pass'] for r in results.values())
    output={'schema_version':1,'status':'promotion-gates-passed','studies':results,'exact_pixels_masks_annotations':True,
            'limits':'One host, three rotating repetitions; dots are observations, not confidence intervals. Absolute y scales differ between workload panels.'}
    (root/'summary.json').write_text(json.dumps(output,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    colors=['#476b82','#d89438']
    for column,(name,result) in enumerate(results.items()):
        arms=result['arms']
        for row,(field,points,label) in enumerate([('median_accepted_per_second','rates','Accepted images / second'),('peak_rss_gib','rss_gib','Peak sampled tree RSS / GiB')]):
            ax=axes[row,column];values=[arms[a][field] for a in ('baseline','current')]
            ax.bar([0,1],values,color=colors,width=.58)
            for x,arm in enumerate(('baseline','current')):
                ax.scatter([x-.07,x,x+.07],arms[arm][points],color='#202a30',s=20,zorder=3)
                ax.text(x,values[x]*1.06,f'{values[x]:.3f}',ha='center')
            ax.set_xticks([0,1],['Batch','Rolling']);ax.set_ylabel(label);ax.set_ylim(0,max(values)*1.25)
            ax.set_title(f'{name.capitalize()}: {arms["baseline"]["samples"]} samples ×3 reps')
    fig.suptitle('Bounded rolling scheduler — local paired production evidence')
    fig.savefig(root/'comparison.png',dpi=150);plt.close(fig)
    rows=''.join(f'<tr><td>{name}</td><td>{r["throughput_gain_fraction"]:+.1%}</td><td>{r["peak_rss_change_fraction"]:+.1%}</td></tr>' for name,r in results.items())
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Rolling scheduler</title><h1>Rolling scheduler</h1><p>'+output['limits']+'</p><img src="comparison.png" alt="Paired throughput and peak RSS"><table><tr><th>Workload</th><th>Median rate change</th><th>Peak RSS change</th></tr>'+rows+'</table>')
    print(json.dumps({k:{key:v[key] for key in ('throughput_gain_fraction','peak_rss_change_fraction')} for k,v in results.items()}))

if __name__=='__main__':main()
