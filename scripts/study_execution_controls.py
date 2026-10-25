"""Fresh-process, rotating-order production policies with exact encoded-image checks.

Raw evidence only. Use --source-root to pin an immutable checkout. No timing gates or default tuning.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import perf_counter

import psutil
import yaml


def process_tree_sample(pid, detailed=False):
    """Observed RSS counts shared pages in each process; useful as a conservative guard."""
    rss=threads=cpu=pss=uss=known=0
    complete=True
    try:
        parent=psutil.Process(pid);processes=[parent,*parent.children(recursive=True)]
    except psutil.Error:return {'rss_bytes':0,'threads':0,'cpu_seconds':0,'pss_bytes':None,'uss_bytes':None,'pss_complete':False}
    for process in processes:
        try:
            rss+=process.memory_info().rss;threads+=process.num_threads()
            times=process.cpu_times();cpu+=times.user+times.system
            if detailed:
                info=process.memory_full_info()
                if not hasattr(info,'pss'):complete=False
                else:pss+=info.pss;uss+=getattr(info,'uss',0);known+=1
        except psutil.Error:complete=False
    return {'rss_bytes':rss,'threads':threads,'cpu_seconds':cpu,
            'pss_bytes':pss if detailed and known else None,'uss_bytes':uss if detailed and known else None,'pss_complete':detailed and complete}


def guard_reason(args,elapsed,memory,swap,tree,initial_swap_out):
    if args.rss_limit_gib and tree['rss_bytes']>args.rss_limit_gib*2**30:return 'process-tree RSS limit'
    if getattr(args,'pss_limit_gib',None) and tree.get('pss_bytes') is not None and tree['pss_bytes']>args.pss_limit_gib*2**30:return 'process-tree PSS limit'
    if args.min_available_gib and memory.available<args.min_available_gib*2**30:return 'available host memory floor'
    if args.max_swap_out_mib and swap.sout-initial_swap_out>args.max_swap_out_mib*2**20:return 'host swap-out limit'
    if args.cell_timeout_seconds and elapsed>args.cell_timeout_seconds:return 'cell timeout'
    return None


def stop_benchmark(process):
    # POSIX sessions isolate the benchmark and all its workers from this driver.
    # Stop the complete session so a coordinator exit cannot orphan stress workers.
    try:children=psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:children=[]
    if os.name=='posix':
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    else:
        for child in children:
            try:child.terminate()
            except psutil.Error:pass
        process.terminate()
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    _,alive=psutil.wait_procs(children,timeout=1)
    for child in alive:
        try:child.kill()
        except psutil.Error:pass
    psutil.wait_procs(alive,timeout=1)


def image_signature(pool):
    records=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines() if line]
    return hashlib.sha256(''.join(hashlib.sha256((pool/r['image_path']).read_bytes()).hexdigest() for r in records).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path('.'))
    parser.add_argument('--compare-source-root',type=Path,help='Optional baseline checkout, interleaved with the primary source per policy')
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--matrix',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--warmups',type=int,default=2)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--rss-limit-gib',type=float,help='Abort a cell above this sampled process-tree RSS')
    parser.add_argument('--pss-limit-gib',type=float,help='Abort above sampled proportional physical memory, where supported')
    parser.add_argument('--detailed-memory',action='store_true',help='Record Linux PSS/USS once per second to distinguish shared pages')
    parser.add_argument('--poll-interval-seconds',type=float,default=.25,help='Guard polling interval, at least0.05 seconds')
    parser.add_argument('--min-available-gib',type=float,help='Abort below this available host-memory floor')
    parser.add_argument('--max-swap-out-mib',type=float,help='Abort on this much additional host swap-out')
    parser.add_argument('--cell-timeout-seconds',type=float,help='Abort a cell exceeding this command duration')
    args=parser.parse_args()
    if not .05<=args.poll_interval_seconds<=2:raise ValueError('Poll interval must be between0.05 and2 seconds')
    if any(value is not None and (not math.isfinite(value) or value<=0) for value in [args.rss_limit_gib,args.pss_limit_gib,args.min_available_gib,args.max_swap_out_mib,args.cell_timeout_seconds]):
        raise ValueError('Guard limits must be positive')
    guarded=any(value is not None for value in [args.rss_limit_gib,args.pss_limit_gib,args.min_available_gib,args.max_swap_out_mib,args.cell_timeout_seconds])
    source=args.source_root.resolve();root=args.output_dir.resolve();config=args.config.resolve()
    matrix=yaml.safe_load(args.matrix.read_text())
    if set(matrix)!={'schema_version','variants'} or matrix['schema_version']!=1 or not matrix['variants']:
        raise ValueError('Strict execution matrix required')
    if root.exists() or args.samples<1 or args.repeats<1 or args.warmups<0: raise ValueError('Fresh output and valid counts required')
    sources={'current':source} if args.compare_source_root else {'configured':source}
    if args.compare_source_root:sources={'baseline':args.compare_source_root.resolve(),**sources}
    provenance={label:{'commit':subprocess.run(['git','rev-parse','HEAD'],cwd=path,check=True,capture_output=True,text=True).stdout.strip(),
        'dirty':bool(subprocess.run(['git','status','--porcelain'],cwd=path,check=True,capture_output=True,text=True).stdout.strip())} for label,path in sources.items()}
    root.mkdir(parents=True)
    policies={}
    for index,(name,policy) in enumerate(matrix['variants'].items()):
        path=root/f'policy-{index}.yaml';path.write_text(yaml.safe_dump({'schema_version':1,'variants':{'configured':policy}}));policies[name]=path
    cases={((label+':'+name) if args.compare_source_root else name):(label,path,policy) for name,policy in policies.items() for label,path in sources.items()}
    names=list(cases);records=[];reference=None;pixel_reference=None
    for repeat in range(args.repeats):
        for name in names[repeat%len(names):]+names[:repeat%len(names)]:
            # Names never enter filesystem paths; strict core validation handles policy leaves.
            index=names.index(name);cell=root/f'{repeat:02d}-{index:02d}'
            implementation,source,policy=cases[name]
            command=[sys.executable,'-m','dataset_generator_m1','benchmark','--production','--config',str(config),'--execution-matrix',str(policy),
                     '--samples',str(args.samples),'--warmup',str(args.warmups),'--repeats','1','--output-dir',str(cell),'--output-format','json']
            (root/'progress.json').write_text(json.dumps({'repeat':repeat,'policy':name,'completed':len(records)}))
            started=perf_counter();system=[];abort=None;initial_swap_out=psutil.swap_memory().sout;last_detailed=-1
            with (root/f'{repeat:02d}-{index:02d}.log').open('w') as log:
                process=subprocess.Popen(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,
                    env={**os.environ,'PYTHONPATH':str(source/'src'),'PYTHONDONTWRITEBYTECODE':'1'},start_new_session=os.name=='posix')
                try:
                    while True:
                        memory,swap=psutil.virtual_memory(),psutil.swap_memory()
                        detailed=(args.detailed_memory or args.pss_limit_gib is not None) and perf_counter()-started-last_detailed>=1
                        tree=process_tree_sample(process.pid,detailed=detailed)
                        if detailed:last_detailed=perf_counter()-started
                        system.append({'elapsed':perf_counter()-started,'available_memory_bytes':memory.available,'swap_used_bytes':swap.used,
                                       'swap_in_bytes':swap.sin,'swap_out_bytes':swap.sout,'cpu_percent':psutil.cpu_percent(None),**tree})
                        abort=guard_reason(args,perf_counter()-started,memory,swap,tree,initial_swap_out)
                        if abort:
                            stop_benchmark(process);code=process.returncode;break
                        try: code=process.wait(timeout=args.poll_interval_seconds if guarded else 2);break
                        except subprocess.TimeoutExpired: pass
                except BaseException as error:
                    # Ctrl+C cannot reach the isolated benchmark session. A
                    # watchdog failure must also stop that complete workload.
                    stop_benchmark(process)
                    (root/f'{repeat:02d}-{index:02d}-system.json').write_text(json.dumps(system))
                    failure={'status':'monitor-interrupted','policy':name,'repeat':repeat,
                             'reason':type(error).__name__,'completed_cells':len(records)}
                    (root/'interruption.json').write_text(json.dumps(failure,indent=2))
                    (root/'progress.json').write_text(json.dumps(failure))
                    raise
            (root/f'{repeat:02d}-{index:02d}-system.json').write_text(json.dumps(system))
            if abort:
                failure={'status':'guard-aborted','policy':name,'repeat':repeat,'reason':abort,'completed_cells':len(records),
                         'peak_observed_rss_bytes':max(s['rss_bytes'] for s in system),'elapsed_seconds':perf_counter()-started,
                         'minimum_available_memory_bytes':min(s['available_memory_bytes'] for s in system),
                         'peak_observed_pss_bytes':max((s['pss_bytes'] for s in system if s['pss_complete']),default=None),
                         'source':provenance[implementation],
                         'guard_limits':{key:getattr(args,key) for key in ['rss_limit_gib','pss_limit_gib','min_available_gib','max_swap_out_mib','cell_timeout_seconds','poll_interval_seconds']}}
                (root/'abort.json').write_text(json.dumps(failure,indent=2));(root/'progress.json').write_text(json.dumps(failure))
                raise RuntimeError(f'Cell aborted by {abort}; raw evidence retained')
            if code: raise RuntimeError(f'Cell {repeat}/{name} failed; inspect log')
            result=json.loads((cell/'benchmark.json').read_text());row=result['records'][0]
            if result['status']!='complete' or row['accepted']!=args.samples: raise RuntimeError('Incomplete or invalid production pool')
            pool=cell/'00-configured'
            pixels=image_signature(pool)
            samples=[json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines() if line]
            caches={}
            for sample in samples:
                execution=sample.get('execution',{});worker=execution.get('worker_pid',0)
                stats=execution.get('decoded_cache',{})
                previous=caches.get(worker,{})
                caches[worker]={key:max(previous.get(key,0),stats.get(key,0)) for key in ['hits','misses','retained_bytes']}
            cache_totals={key:sum(v[key] for v in caches.values()) for key in ['hits','misses','retained_bytes']}
            reference=reference or row['content_signature'];pixel_reference=pixel_reference or pixels
            if reference!=row['content_signature'] or pixel_reference!=pixels: raise RuntimeError('Execution policy changed pixels/geometry/masks/annotations')
            records.append({**row,'variant':name,'repeat':repeat,'pixel_signature':pixels,'software':result['software'],'cache_observed':cache_totals,
                'source':provenance[implementation],'implementation':implementation,'command_seconds':perf_counter()-started,
                'minimum_available_memory_bytes':min(s['available_memory_bytes'] for s in system),
                'maximum_swap_used_bytes':max(s['swap_used_bytes'] for s in system),
                'swap_in_delta_bytes':system[-1]['swap_in_bytes']-system[0]['swap_in_bytes'],
                'swap_out_delta_bytes':system[-1]['swap_out_bytes']-system[0]['swap_out_bytes'],
                'command_resource_observed':{'peak_rss_bytes':max(s['rss_bytes'] for s in system),
                    'peak_threads':max(s['threads'] for s in system),
                    'peak_pss_bytes':max((s['pss_bytes'] for s in system if s['pss_complete']),default=None),
                    'peak_uss_bytes':max((s['uss_bytes'] for s in system if s['pss_complete']),default=None)},
                'guard_limits':{key:getattr(args,key) for key in ['rss_limit_gib','pss_limit_gib','min_available_gib','max_swap_out_mib','cell_timeout_seconds','poll_interval_seconds']}})
            summary={'schema_version':1,'kind':'execution-control-study','status':'running','samples':args.samples,'warmups':args.warmups,'repeats':args.repeats,
                'low_sample':args.samples<20 or args.repeats<3,'exact_encoded_images_equal':True,'geometry_annotation_masks_equal':True,'records':records}
            (root/'summary.json').write_text(json.dumps(summary,indent=2))
            print(f'{repeat+1}/{args.repeats} {name}: {row["throughput"]:.3f} accepted/s, RSS {row["resource_peaks"]["rss_bytes"]/1024**3:.2f}GiB',flush=True)
    summary['status']='complete';(root/'summary.json').write_text(json.dumps(summary,indent=2))
    (root/'progress.json').write_text(json.dumps({'status':'complete','cells':len(records)}))

if __name__=='__main__':main()
