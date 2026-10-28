"""Coordinator behavior around real worker processes and fake capability probes."""
import copy
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from dataset_generator_m1 import blender_pilot as pilot
from dataset_generator_m1 import blender_runner as runner
from dataset_generator_m1.blender_execution import load_catalog


def test_coordinator_partitions_jobs_once_and_freezes_hardware(tmp_path,monkeypatch):
    catalog=load_catalog().model_dump(mode='json');hardware={'cpu_count':2,'environment':'colab','devices':[{'name':'Tesla T4','id':'gpu0','backend':'OPTIX','oidn_gpu':True,'memory_mib':15360}]}
    study={'identity':'study','execution_catalog':catalog,'config':{'resolution':[640,640]}}
    seen=[];done=set()
    def monitor(commands,root,name,seconds,guards,**kwargs):
        seen.append((commands,seconds))
        if name.startswith('probe'):
            from pathlib import Path
            Path(commands[0][4]).write_text(json.dumps(hardware))
        else:
            for command in commands:done.update(command[command.index('--jobs')+1:command.index('--blender-install-path')])
        return {'status':'complete','command_seconds':2}
    monkeypatch.setattr(runner,'monitor',monitor)
    monkeypatch.setattr(pilot,'completed_outputs',lambda *args:[({'id':x},None,None) for x in done])
    result=runner.execute(tmp_path,study,'bproc','blender',{'c','b','a'},[],100)
    assert result['workers']==2 and result['execution_profile']=='colab-t4-small'
    assert seen[1][1]==98
    commands=seen[1][0];assigned=[arg for command in commands for arg in command[command.index('--jobs')+1:command.index('--blender-install-path')]]
    assert sorted(assigned)==['a','b','c']
    original=(tmp_path/'execution.json').read_bytes();hardware['cpu_count']=1
    with pytest.raises(ValueError,match='selection changed'):runner.execute(tmp_path,study,'bproc','blender',{'a'},[],100)
    assert (tmp_path/'execution.json').read_bytes()==original and len(seen)==3


def test_successful_worker_exit_with_missing_jobs_is_failure(tmp_path,monkeypatch):
    catalog=load_catalog().model_dump(mode='json')
    def monitor(commands,root,name,*args,**kwargs):
        if name.startswith('probe'):
            from pathlib import Path
            Path(commands[0][4]).write_text(json.dumps({'cpu_count':2,'devices':[],'environment':'local'}))
        return {'status':'complete','command_seconds':1}
    monkeypatch.setattr(runner,'monitor',monitor);monkeypatch.setattr(pilot,'completed_outputs',lambda *args:[])
    study={'identity':'s','execution_catalog':catalog,'config':{'resolution':[640,640]}}
    result=runner.execute(tmp_path,study,'bproc','blender',{'a'},[],100)
    assert result['status']=='failed' and result['reason']=='worker-finished-with-missing-scenes'


@pytest.mark.parametrize('failure',[KeyboardInterrupt,RuntimeError])
def test_monitor_interruptions_stop_every_worker(tmp_path,monkeypatch,failure):
    import psutil
    original=subprocess.Popen;started=[]
    def launch(command,**kwargs):
        p=original(command,**kwargs);started.append(p);return p
    monkeypatch.setattr(runner.subprocess,'Popen',launch)
    monkeypatch.setattr(psutil,'virtual_memory',lambda:(_ for _ in ()).throw(failure('injected')))
    guards={'min_available_gib':2,'rss_limit_gib':10,'max_swap_out_mib':16}
    result=runner.monitor([[sys.executable,'-c','import time;time.sleep(60)']]*2,tmp_path,'case',10,guards)
    assert len(started)==2 and all(p.poll() is not None for p in started)
    assert result['status']==('interrupted' if failure==KeyboardInterrupt else 'guard-aborted')


def test_monitor_aggregates_worker_rss_before_guarding(tmp_path,monkeypatch):
    import psutil
    original=subprocess.Popen;started=[]
    def launch(command,**kwargs):
        p=original(command,**kwargs);started.append(p);return p
    monkeypatch.setattr(runner.subprocess,'Popen',launch)
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(children=lambda **kw:[],memory_info=lambda:SimpleNamespace(rss=3*2**30)))
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=8*2**30))
    monkeypatch.setattr(psutil,'swap_memory',lambda:SimpleNamespace(sout=0))
    guards={'min_available_gib':2,'rss_limit_gib':4,'max_swap_out_mib':16}
    result=runner.monitor([[sys.executable,'-c','import time;time.sleep(60)']]*2,tmp_path,'case',10,guards)
    assert result['reason']=='process-tree-RSS' and result['peak_rss_bytes']==6*2**30
    assert all(p.poll() is not None for p in started)


@pytest.mark.skipif(sys.platform=='win32',reason='POSIX process groups')
def test_monitor_reaps_orphan_when_wrapper_exits_before_first_sample(tmp_path):
    import os,time,psutil
    pidfile=tmp_path/'child.pid'
    child="import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);open(os.environ['PIDFILE'],'w').write(str(os.getpid()));time.sleep(60)"
    parent="import subprocess,sys,os,time;subprocess.Popen([sys.executable,'-c',sys.argv[1]],env={**os.environ,'PIDFILE':sys.argv[2]});time.sleep(.1)"
    guards={'min_available_gib':.001,'rss_limit_gib':100,'max_swap_out_mib':1000}
    result=runner.monitor([[sys.executable,'-c',parent,child,str(pidfile)]],tmp_path,'orphan',5,guards)
    assert result['status']=='complete'
    if pidfile.exists():
        try:p=psutil.Process(int(pidfile.read_text()))
        except psutil.NoSuchProcess:return
        try:
            p.wait(timeout=2)
        except psutil.TimeoutExpired:
            assert p.status()==psutil.STATUS_ZOMBIE


def test_gpu_free_memory_guard_stops_workers(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs:
        subprocess.CompletedProcess(args[0], 0, stdout='80, 23000, 500\n'))
    guards={'min_available_gib':0.001,'rss_limit_gib':100,'max_swap_out_mib':1000,'min_gpu_free_mib':1000}
    result=runner.monitor([[sys.executable,'-c','import time; time.sleep(60)']],tmp_path,'gpu',10,guards,gpu=True)
    assert result['status']=='guard-aborted' and result['reason']=='gpu-memory-floor'
    assert json.loads((tmp_path/'gpu-gpu.json').read_text())[0]['devices'][0]['free_memory_mib']==500


def test_gpu_guard_fails_closed_if_telemetry_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH',str(tmp_path))
    guards={'min_available_gib':0.001,'rss_limit_gib':100,'max_swap_out_mib':1000,'min_gpu_free_mib':1000}
    result=runner.monitor([[sys.executable,'-c','import time; time.sleep(60)']],tmp_path,'gpu-missing',10,guards,gpu=True)
    assert result['reason']=='gpu-telemetry-unavailable' and result['status']=='guard-aborted'


def test_gpu_guard_rejects_stale_telemetry_after_initial_success(tmp_path, monkeypatch):
    import subprocess
    calls=[]
    def gpu_sample(command, **kwargs):
        calls.append(command)
        if len(calls) > 1:
            raise subprocess.CalledProcessError(1,command)
        return subprocess.CompletedProcess(command,0,stdout='80, 1000, 23000\n')
    monkeypatch.setattr(runner.subprocess,'run',gpu_sample)
    guards={'min_available_gib':0.001,'rss_limit_gib':100,'max_swap_out_mib':1000,'min_gpu_free_mib':1000}
    result=runner.monitor([[sys.executable,'-c','import time; time.sleep(60)']],tmp_path,'gpu-stale',10,guards,gpu=True)
    assert len(calls)>=2
    assert result['reason']=='gpu-telemetry-unavailable' and result['status']=='guard-aborted'
