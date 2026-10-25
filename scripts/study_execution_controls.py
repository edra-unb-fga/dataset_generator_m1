"""Fresh-process, rotating-order production policies with exact encoded-image checks.

Raw evidence only. Use --source-root to pin an immutable checkout. No timing gates or default tuning.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import psutil
import yaml


def image_signature(pool):
    records=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines() if line]
    return hashlib.sha256(''.join(hashlib.sha256((pool/r['image_path']).read_bytes()).hexdigest() for r in records).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path('.'))
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--matrix',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--warmups',type=int,default=2)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    source=args.source_root.resolve();root=args.output_dir.resolve();config=args.config.resolve()
    matrix=yaml.safe_load(args.matrix.read_text())
    if set(matrix)!={'schema_version','variants'} or matrix['schema_version']!=1 or not matrix['variants']:
        raise ValueError('Strict execution matrix required')
    if root.exists() or args.samples<1 or args.repeats<1 or args.warmups<0: raise ValueError('Fresh output and valid counts required')
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=source,check=True,capture_output=True,text=True).stdout.strip()
    dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=source,check=True,capture_output=True,text=True).stdout.strip())
    root.mkdir(parents=True)
    policies={}
    for index,(name,policy) in enumerate(matrix['variants'].items()):
        path=root/f'policy-{index}.yaml';path.write_text(yaml.safe_dump({'schema_version':1,'variants':{'configured':policy}}));policies[name]=path
    names=list(policies);records=[];reference=None;pixel_reference=None
    for repeat in range(args.repeats):
        for name in names[repeat%len(names):]+names[:repeat%len(names)]:
            # Names never enter filesystem paths; strict core validation handles policy leaves.
            index=names.index(name);cell=root/f'{repeat:02d}-{index:02d}'
            command=[sys.executable,'-m','dataset_generator_m1','benchmark','--production','--config',str(config),'--execution-matrix',str(policies[name]),
                     '--samples',str(args.samples),'--warmup',str(args.warmups),'--repeats','1','--output-dir',str(cell),'--output-format','json']
            (root/'progress.json').write_text(json.dumps({'repeat':repeat,'policy':name,'completed':len(records)}))
            started=perf_counter();system=[]
            with (root/f'{repeat:02d}-{index:02d}.log').open('w') as log:
                process=subprocess.Popen(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,
                    env={**os.environ,'PYTHONPATH':str(source/'src'),'PYTHONDONTWRITEBYTECODE':'1'})
                while True:
                    memory,swap=psutil.virtual_memory(),psutil.swap_memory()
                    system.append({'elapsed':perf_counter()-started,'available_memory_bytes':memory.available,'swap_used_bytes':swap.used,
                                   'swap_in_bytes':swap.sin,'swap_out_bytes':swap.sout,'cpu_percent':psutil.cpu_percent(None)})
                    try: code=process.wait(timeout=2);break
                    except subprocess.TimeoutExpired: pass
            (root/f'{repeat:02d}-{index:02d}-system.json').write_text(json.dumps(system))
            if code: raise RuntimeError(f'Cell {repeat}/{name} failed; inspect log')
            result=json.loads((cell/'benchmark.json').read_text());row=result['records'][0]
            if result['status']!='complete' or row['accepted']!=args.samples: raise RuntimeError('Incomplete or invalid production pool')
            pixels=image_signature(cell/'00-configured')
            reference=reference or row['content_signature'];pixel_reference=pixel_reference or pixels
            if reference!=row['content_signature'] or pixel_reference!=pixels: raise RuntimeError('Execution policy changed pixels/geometry/masks/annotations')
            records.append({**row,'variant':name,'repeat':repeat,'pixel_signature':pixels,'software':result['software'],
                'source':{'commit':commit,'dirty':dirty},'command_seconds':perf_counter()-started,
                'minimum_available_memory_bytes':min(s['available_memory_bytes'] for s in system),
                'maximum_swap_used_bytes':max(s['swap_used_bytes'] for s in system),
                'swap_in_delta_bytes':system[-1]['swap_in_bytes']-system[0]['swap_in_bytes'],
                'swap_out_delta_bytes':system[-1]['swap_out_bytes']-system[0]['swap_out_bytes']})
            summary={'schema_version':1,'kind':'execution-control-study','status':'running','samples':args.samples,'warmups':args.warmups,'repeats':args.repeats,
                'low_sample':args.samples<20 or args.repeats<3,'exact_encoded_images_equal':True,'geometry_annotation_masks_equal':True,'records':records}
            (root/'summary.json').write_text(json.dumps(summary,indent=2))
            print(f'{repeat+1}/{args.repeats} {name}: {row["throughput"]:.3f} accepted/s, RSS {row["resource_peaks"]["rss_bytes"]/1024**3:.2f}GiB',flush=True)
    summary['status']='complete';(root/'summary.json').write_text(json.dumps(summary,indent=2))
    (root/'progress.json').write_text(json.dumps({'status':'complete','cells':len(records)}))

if __name__=='__main__':main()
