"""Detached Colab controller: stage inputs, execute, retrieve evidence, stop.

The watchdog independently releases the named runtime if the controller hangs.
A computer shutdown, network failure, or revoked credentials can still defeat cleanup.
"""
import argparse, json, os, secrets, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from colab_transport import call as transport_call, sha, write

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--colab', default='colab')
p.add_argument('--session', default='ground-material-20261029')
p.add_argument('--input-dir', default=str(Path(__file__).resolve().parent))
p.add_argument('--scripts-dir', default=str(Path(__file__).resolve().parent))
p.add_argument('--watchdog-seconds', type=int, default=1500)
p.add_argument('--watchdog', action='store_true')
a = p.parse_args(); out = Path(a.output)
status_file = out/'status.json'
def status(step, **extra):
    value = {'step':step, 'pid':os.getpid(), 'timestamp':time.time(), 'session':a.session, **extra}
    write(status_file, value)
def call(*args, timeout=180, check=True):
    print('COMMAND', args[0], flush=True)
    return transport_call(a.colab, '--config', str(out/'colab-sessions.json'), *args, timeout=timeout, check=check)

def preflight():
    inp=Path(a.input_dir); scripts=Path(a.scripts_dir)
    for name in ('input.tar.gz','input.tar.gz.run.py','spec.json','matrix.json'):
        if not (inp/name).is_file() or not (inp/name).stat().st_size: raise ValueError('Missing or empty input: '+name)
    if not (scripts/'remote.py').is_file(): raise ValueError('Missing remote.py')
    spec=json.loads((inp/'spec.json').read_text())
    for name,key in (('input.tar.gz','bundle_sha256'),('input.tar.gz.run.py','bootstrap_sha256'),('matrix.json','matrix_sha256')):
        if sha(inp/name)!=spec.get(key): raise ValueError('Input checksum mismatch: '+name)
    duration=spec.get('total_seconds')
    if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0 < duration <= 1200:
        raise ValueError('total_seconds must be greater than 0 and at most 1200')
    if a.watchdog_seconds < duration+180:
        raise ValueError('watchdog deadline must allow at least 180 seconds beyond remote budget')

if a.watchdog:
    time.sleep(a.watchdog_seconds)
    try:
        current = json.loads(status_file.read_text())
        if current.get('step') == 'closed' and current.get('stop_confirmed'): sys.exit(0)
    except (OSError, ValueError): pass
    print('WATCHDOG: attempting to stop the study runtime', flush=True)
    for _ in range(3):
        try:
            if call('stop', '-s', a.session, timeout=90, check=False).returncode == 0: break
        except (OSError, subprocess.TimeoutExpired): pass
        time.sleep(30)
    sys.exit(0)
preflight()
out.mkdir(parents=True, exist_ok=False)
a.session = a.session + '-' + secrets.token_hex(6)
log = (out/'watchdog.log').open('x')
subprocess.Popen([sys.executable, __file__, '--watchdog', '--output', str(out), '--colab', a.colab, '--session', a.session, '--watchdog-seconds', str(a.watchdog_seconds)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
error = None; stop_ok = False; retrieved = False
try:
    status('allocating')
    call('new', '-s', a.session, '--gpu', 'L4', timeout=240)
    status('allocated')
    call('usage', timeout=90, check=False)
    inp = Path(a.input_dir); scripts = Path(a.scripts_dir)
    uploads = ['input.tar.gz','input.tar.gz.run.py','spec.json','matrix.json']
    for filename in uploads:
        local, remote = inp/filename, '/content/'+filename
        status('uploading', file=local.name)
        call('upload', '-s', a.session, str(local), remote, timeout=240)
    status('executing')
    call('exec', '-s', a.session, '--timeout', '1300', '-f', str(scripts/'remote.py'), timeout=1350)
except BaseException as exc:
    error = f'{type(exc).__name__}: {exc}'; print('ERROR', error, flush=True)
finally:
    # Always try to retrieve even when execution timed out or reported an error.
    status('retrieving', error=error)
    try:
        call('download', '-s', a.session, '/content/ground-results.json', str(out/'result-metadata.json'), timeout=180)
        meta = json.loads((out/'result-metadata.json').read_text())
        if not meta.get('sha256'): raise RuntimeError('remote archive was not created')
        partial = out/'results.tar.gz.partial'
        call('download', '-s', a.session, '/content/ground-results.tar.gz', str(partial), timeout=300)
        if sha(partial) != meta['sha256'] or partial.stat().st_size != meta['bytes']: raise RuntimeError('download checksum or size mismatch')
        os.replace(partial, out/'results.tar.gz'); retrieved = True
        if meta['status'] != 'complete': error = error or f"remote {meta['status']}: {meta.get('error')}"
    except BaseException as exc:
        error = error or f'retrieval {type(exc).__name__}: {exc}'; print('RETRIEVAL ERROR', str(exc), flush=True)
    status('stopping', error=error, retrieved=retrieved)
    for attempt in range(3):
        try:
            if call('stop', '-s', a.session, timeout=90, check=False).returncode == 0: stop_ok = True; break
        except (OSError, subprocess.TimeoutExpired) as exc: print('STOP ERROR', str(exc), flush=True)
        time.sleep(10)
    try: call('usage', timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired): pass
    status('closed' if stop_ok else 'stop-unconfirmed', error=error, retrieved=retrieved, stop_confirmed=stop_ok)

if error is not None or not stop_ok or not retrieved:
    sys.exit(1)
