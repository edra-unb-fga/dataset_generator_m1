"""Detached Colab controller: stage inputs, execute, retrieve evidence, stop.

The watchdog independently releases the named runtime if the controller hangs.
A computer shutdown, network failure, or revoked credentials can still defeat cleanup.
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--colab', default='colab')
p.add_argument('--session', default='realism-camera-adjusted-20261028')
p.add_argument('--input-dir', default=str(Path(__file__).resolve().parent))
p.add_argument('--scripts-dir', default=str(Path(__file__).resolve().parent))
p.add_argument('--watchdog-seconds', type=int, default=3000)
p.add_argument('--watchdog', action='store_true')
a = p.parse_args(); out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
status_file = out/'status.json'
def status(step, **extra):
    value = {'step':step, 'pid':os.getpid(), 'timestamp':time.time(), **extra}
    tmp = out/'status.tmp'; tmp.write_text(json.dumps(value, indent=2)); os.replace(tmp, status_file)
def call(*args, timeout=180, check=True):
    print('COMMAND', args[0], flush=True)
    r = subprocess.run([a.colab, '--auth=oauth2', *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    # Failed proxy requests can print temporary credentials in their URL.
    safe_output = re.sub(r'(?i)(colab-runtime-proxy-token=)[^\s&]+', r'\1[REDACTED]', r.stdout)
    print(safe_output, flush=True)
    if check and r.returncode: raise RuntimeError(f'{args[0]} returned {r.returncode}')
    return r
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
log = (out/'watchdog.log').open('a')
subprocess.Popen([sys.executable, __file__, '--watchdog', '--output', str(out), '--colab', a.colab, '--session', a.session, '--watchdog-seconds', str(a.watchdog_seconds)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
error = None; stop_ok = False; retrieved = False
try:
    status('allocating')
    call('new', '-s', a.session, '--gpu', 'L4', timeout=240)
    status('allocated')
    call('usage', timeout=90, check=False)
    inp = Path(a.input_dir); scripts = Path(a.scripts_dir)
    uploads = ['development-input.tar.gz','development-input.tar.gz.run.py','holdout-input.tar.gz','development-matrix.json','holdout-matrix.json','quality-matrix.json','completion-plan.json','speed.py']
    for filename in uploads:
        local, remote = inp/filename, '/content/'+filename
        status('uploading', file=local.name)
        call('upload', '-s', a.session, str(local), remote, timeout=240)
    status('executing')
    call('exec', '-s', a.session, '--timeout', '2200', '-f', str(scripts/'remote.py'), timeout=2280)
except BaseException as exc:
    error = f'{type(exc).__name__}: {exc}'; print('ERROR', error, flush=True)
finally:
    # Always try to retrieve even when execution timed out or reported an error.
    status('retrieving', error=error)
    try:
        call('download', '-s', a.session, '/content/camera-results.json', str(out/'result-metadata.json'), timeout=180)
        meta = json.loads((out/'result-metadata.json').read_text())
        if not meta.get('sha256'): raise RuntimeError('remote archive was not created')
        partial = out/'results.tar.gz.partial'
        call('download', '-s', a.session, '/content/camera-results.tar.gz', str(partial), timeout=300)
        h = hashlib.sha256()
        with partial.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024), b''): h.update(block)
        if h.hexdigest() != meta['sha256'] or partial.stat().st_size != meta['bytes']: raise RuntimeError('download checksum or size mismatch')
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
