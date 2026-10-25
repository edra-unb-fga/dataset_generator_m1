import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest

spec=importlib.util.spec_from_file_location('execution_study',Path(__file__).parents[1]/'scripts/study_execution_controls.py')
study=importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_guard_units_and_thresholds():
    args=SimpleNamespace(rss_limit_gib=4,min_available_gib=1,max_swap_out_mib=64,cell_timeout_seconds=60)
    memory=SimpleNamespace(available=2*2**30);swap=SimpleNamespace(sout=0);tree={'rss_bytes':3*2**30}
    assert study.guard_reason(args,10,memory,swap,tree,0) is None
    assert 'RSS' in study.guard_reason(args,10,memory,swap,{'rss_bytes':5*2**30},0)
    assert 'memory floor' in study.guard_reason(args,10,SimpleNamespace(available=2**29),swap,tree,0)
    assert 'swap-out' in study.guard_reason(args,10,memory,SimpleNamespace(sout=65*2**20),tree,0)
    assert 'timeout' in study.guard_reason(args,61,memory,swap,tree,0)


@pytest.mark.skipif(os.name!='posix',reason='POSIX benchmark session cleanup')
def test_guard_stops_child_even_if_coordinator_exits_first():
    child_code="import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ready',flush=True);time.sleep(60)"
    parent_code="import subprocess,sys,time;child=subprocess.Popen([sys.executable,'-c',sys.argv[1]],stdout=subprocess.PIPE,text=True);child.stdout.readline();print(child.pid,flush=True);time.sleep(60)"
    process=subprocess.Popen([sys.executable,'-c',parent_code,child_code],stdout=subprocess.PIPE,text=True,start_new_session=True)
    child=None
    try:
        child=psutil.Process(int(process.stdout.readline()))
        study.stop_benchmark(process)
        assert process.poll() is not None
        assert not child.is_running() or child.status()==psutil.STATUS_ZOMBIE
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=3)
        if child is not None:
            try:child.kill()
            except psutil.Error:pass
