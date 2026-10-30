import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SUPERVISOR=ROOT/'experiments/blenderproc/studies/procedural-scenes/supervisor.py'
REMOTE=SUPERVISOR.with_name('remote.py')

def files(tmp_path):
    inp=tmp_path/'input';inp.mkdir()
    for name in ('input.tar.gz','input.tar.gz.run.py','generate_scene_presets.py'):
        (inp/name).write_bytes(name.encode())
    sha=lambda name: hashlib.sha256((inp/name).read_bytes()).hexdigest()
    spec={'bundle_sha256':sha('input.tar.gz'),'bootstrap_sha256':sha('input.tar.gz.run.py'),'cli_sha256':sha('generate_scene_presets.py'),'total_seconds':100}
    (inp/'spec.json').write_text(json.dumps(spec));return inp

def test_preflight_rejects_before_allocation_and_preserves_output(tmp_path):
    inp=files(tmp_path);(inp/'input.tar.gz').write_bytes(b'changed')
    marker=tmp_path/'allocated';fake=tmp_path/'colab';fake.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n');fake.chmod(0o755)
    out=tmp_path/'out'
    result=subprocess.run([sys.executable,str(SUPERVISOR),'--colab',str(fake),'--input-dir',str(inp),'--output',str(out)],capture_output=True,text=True)
    assert result.returncode != 0 and 'checksum mismatch' in result.stderr
    assert not marker.exists() and not out.exists()

def test_remote_archives_prebootstrap_failure(tmp_path):
    content=tmp_path/'content';content.mkdir()
    (content/'spec.json').write_text(json.dumps({'bootstrap_sha256':'incorrect','cli_sha256':'incorrect','total_seconds':30}))
    (content/'input.tar.gz.run.py').write_text('bad')
    script=tmp_path/'remote.py';script.write_text(REMOTE.read_text().replace("c=Path('/content')",'c=Path('+repr(str(content))+')'))
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert result.returncode==0
    metadata=json.loads((content/'procedural-results.json').read_text())
    assert metadata['status']=='failed' and 'Checksum mismatch' in metadata['error']
    assert (content/'procedural-results.tar.gz').is_file()

def test_existing_output_and_short_deadline_fail_without_allocation(tmp_path):
    inp=files(tmp_path);marker=tmp_path/'called';fake=tmp_path/'colab';fake.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n');fake.chmod(0o755)
    out=tmp_path/'existing';out.mkdir();(out/'status.json').write_text('original')
    command=[sys.executable,str(SUPERVISOR),'--colab',str(fake),'--input-dir',str(inp),'--output',str(out)]
    assert subprocess.run(command,capture_output=True).returncode != 0
    assert (out/'status.json').read_text()=='original' and not marker.exists()
    command[-1]=str(tmp_path/'fresh');command += ['--watchdog-seconds','200']
    assert subprocess.run(command,capture_output=True).returncode != 0
    assert not marker.exists()


def test_controller_failure_returns_nonzero_and_stops(tmp_path, monkeypatch):
    import runpy
    import pytest
    inp=files(tmp_path);out=tmp_path/'out';calls=[]
    class Result:
        stdout='';returncode=0
    def fake_run(args,**kwargs):
        command=args[args.index('--config')+2];calls.append(command)
        result=Result()
        if command in ('exec','download'):result.returncode=1
        return result
    monkeypatch.setattr(subprocess,'run',fake_run)
    monkeypatch.setattr(subprocess,'Popen',lambda *args,**kwargs: None)
    monkeypatch.setattr(sys,'argv',[str(SUPERVISOR),'--input-dir',str(inp),'--output',str(out)])
    with pytest.raises(SystemExit) as exc:runpy.run_path(str(SUPERVISOR),run_name='__main__')
    assert exc.value.code==1 and 'stop' in calls
    status=json.loads((out/'status.json').read_text())
    assert status['step']=='closed' and status['stop_confirmed'] and status['error']

def test_unconfirmed_stop_exits_nonzero(tmp_path, monkeypatch):
    import runpy
    import time
    import pytest
    inp=files(tmp_path);out=tmp_path/'out'
    class Result:
        stdout='';returncode=0
    def fake_run(args,**kwargs):
        command=args[args.index('--config')+2]
        result=Result()
        if command in ('download','stop'):result.returncode=1
        return result
    monkeypatch.setattr(subprocess,'run',fake_run)
    monkeypatch.setattr(subprocess,'Popen',lambda *args,**kwargs: None)
    monkeypatch.setattr(time,'sleep',lambda _:None)
    monkeypatch.setattr(sys,'argv',[str(SUPERVISOR),'--input-dir',str(inp),'--output',str(out)])
    with pytest.raises(SystemExit) as exc:runpy.run_path(str(SUPERVISOR),run_name='__main__')
    assert exc.value.code==1
    status=json.loads((out/'status.json').read_text())
    assert status['step']=='stop-unconfirmed' and not status['stop_confirmed']
