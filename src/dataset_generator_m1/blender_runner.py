"""Bounded coordinator for capability discovery and isolated Blender workers."""
import json
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic

from .blender_execution import resolve_execution


def monitor(commands, root, name, seconds, guards, *, gpu=False):
    import psutil
    from .blender_pilot import atomic_json
    started=monotonic();swap0=psutil.swap_memory().sout;observations=[];gpu_samples=[];reason=None
    processes=[];logs=[];last_gpu=-1
    try:
        for index,command in enumerate(commands):
            log=(root/f'{name}-worker-{index}.log').open('w');logs.append(log)
            processes.append(subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name=='posix',
                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','MPLBACKEND':'Agg',
                     'MPLCONFIGDIR':str(root/f'mpl-{name}-{index}'),
                     'BLENDER_USER_CONFIG':str(root/f'blender-config-{name}-{index}')}))
        while True:
            rss=0
            for process in processes:
                try:parent=psutil.Process(process.pid);tree=[parent,*parent.children(recursive=True)]
                except psutil.Error:tree=[]
                for child in tree:
                    try:rss+=child.memory_info().rss
                    except psutil.Error:pass
            elapsed=monotonic()-started;available=psutil.virtual_memory().available;swap=max(0,psutil.swap_memory().sout-swap0)
            observations.append({'seconds':elapsed,'rss_bytes':rss,'available_bytes':available,'swap_out_delta_bytes':swap})
            if gpu and elapsed-last_gpu>=1:
                last_gpu=elapsed
                try:
                    usage=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
                    values=[list(map(float,line.split(','))) for line in usage.stdout.splitlines()]
                    gpu_samples.append({'seconds':elapsed,'devices':[{'utilization_percent':x[0],'memory_mib':x[1]} for x in values]})
                except (OSError,ValueError,subprocess.TimeoutExpired):pass
            reason=('available-memory-floor' if available<guards['min_available_gib']*2**30 else
                    'process-tree-RSS' if rss>guards['rss_limit_gib']*2**30 else
                    'host-swap-out' if swap>guards['max_swap_out_mib']*2**20 else
                    'study-time-budget' if elapsed>=seconds else None)
            atomic_json(root/'progress.json',{'status':'running','phase':name,'elapsed_seconds':elapsed,
                'remaining_budget_seconds':max(0,seconds-elapsed),'completed_scenes':len(list((root/'scenes').glob('*/result.json')))})
            if reason or all(p.poll() is not None for p in processes):break
            # No blocking worker wait: resources cover the entire concurrent process group.
            import time
            time.sleep(.25)
    except KeyboardInterrupt:reason='keyboard-interrupted'
    except Exception as error:reason='monitor-failed: '+type(error).__name__
    finally:
        descendants=[]
        for process in processes:
            try:descendants.extend(psutil.Process(process.pid).children(recursive=True))
            except psutil.Error:pass
            try:
                if os.name=='posix':os.killpg(process.pid,signal.SIGTERM)
                else:process.terminate()
            except (ProcessLookupError,OSError):pass
        for process in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if os.name=='posix':
            for process in processes:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        for child in descendants:
            try:child.kill()
            except psutil.Error:pass
        psutil.wait_procs(descendants,timeout=3)
        for log in logs:log.close()
    codes=[p.returncode for p in processes]
    record={'phase':name,'status':'budget-limited' if reason=='study-time-budget' else 'interrupted' if reason=='keyboard-interrupted' else 'guard-aborted' if reason else 'complete' if codes and all(c==0 for c in codes) else 'failed',
            'reason':reason,'returncodes':codes,'command_seconds':monotonic()-started,
            'peak_rss_bytes':max((o['rss_bytes'] for o in observations),default=0),
            'minimum_available_bytes':min((o['available_bytes'] for o in observations),default=None),
            'swap_out_delta_bytes':max((o['swap_out_delta_bytes'] for o in observations),default=0),'guards':guards,
            'sampled_peak_gpu_memory_mib':max((d['memory_mib'] for sample in gpu_samples for d in sample['devices']),default=None)}
    atomic_json(root/f'{name}-resources.json',observations)
    atomic_json(root/f'{name}-gpu.json',gpu_samples)
    return record


def execute(root, study, blenderproc, install, selected, previous, remaining):
    from .blender_pilot import atomic_json, completed_outputs
    catalog=study['execution_catalog'];guards=catalog['guards']
    directory=Path(__file__).resolve().parents[2]/'experiments/blenderproc'
    def command(script,*arguments,temp):
        return [str(Path(blenderproc).resolve()),'run',str(script),*map(str,arguments),
                '--blender-install-path',str(Path(install).resolve()),'--temp-dir',str(root/temp)]
    def record(value):
        previous.append(value);atomic_json(root/'runs.json',previous);atomic_json(root/'progress.json',value)
    index=len(previous);probe_file=root/f'hardware-{index:02d}.json';request=root/'execution-catalog.json'
    atomic_json(request,catalog)
    probe=monitor([command(directory/'probe.py',request,probe_file,temp='probe-temp')],root,f'probe-{index:02d}',min(remaining,guards['probe_timeout_seconds']),guards)
    record(probe)
    if probe['status']!='complete':return probe
    hardware=json.loads(probe_file.read_text())
    config=study['config'];selection=resolve_execution(catalog,hardware,config['resolution'],profile=config.get('execution_profile','auto'),threads=config.get('threads'),workers=config.get('workers'))
    value={'study_identity':study['identity'],'selection':selection}
    destination=root/'execution.json'
    if destination.exists() and json.loads(destination.read_text())!=value:
        raise ValueError('Hardware/execution selection changed; prepare a fresh study')
    atomic_json(destination,value)
    completed={job['id'] for job,path,row in completed_outputs(root,study)}
    todo=sorted(selected-completed)
    if not todo:return {'status':'complete','selected_jobs':sorted(selected),'execution':selection,'command_seconds':0}
    remaining-=probe['command_seconds']
    if remaining<=0:return {'status':'budget-limited','execution':selection,'command_seconds':0}
    count=min(selection['settings']['workers'],len(todo));commands=[]
    for worker in range(count):
        commands.append(command(directory/'render.py',root/'study.json','--execution',destination,'--jobs',*todo[worker::count],temp=f'worker-{worker}-temp'))
    outcome=monitor(commands,root,f'run-{len(previous):02d}',remaining,guards,gpu=selection['settings']['device']=='GPU')
    outcome.update(selected_jobs=sorted(selected),workers=count,execution_identity=selection['identity'],execution_profile=selection['profile'])
    done={job['id'] for job,path,row in completed_outputs(root,study)}
    if outcome['status']=='complete' and selected-done:
        outcome.update(status='failed',reason='worker-finished-with-missing-scenes')
    record(outcome)
    return outcome
