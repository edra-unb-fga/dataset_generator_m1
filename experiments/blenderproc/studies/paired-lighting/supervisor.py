"""Detached Colab controller: stage inputs, execute, retrieve evidence, stop.

The watchdog independently releases the named runtime if the controller hangs.
A computer shutdown, network failure, or revoked credentials can still defeat cleanup.
"""
import argparse, json, math, os, re, secrets, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from colab_transport import call as transport_call, sha, write, split_bundle
from colab_budget import parse_usage, check_aggregate_budget

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--colab', default='colab')
p.add_argument('--session', default='procedural-scenes-20261029')
p.add_argument('--input-dir', default=str(Path(__file__).resolve().parent))
p.add_argument('--scripts-dir', default=str(Path(__file__).resolve().parent))
p.add_argument('--watchdog-seconds', type=int, default=1050)
p.add_argument('--watchdog', action='store_true')
p.add_argument('--rate-evidence', required=False, help='Prior single-L4 controller usage log')
p.add_argument('--budget-baseline', required=False, help='Usage snapshot before the first study attempt')
p.add_argument('--prior-spend-reserve', type=float, required=False, help='Conservative CU reserve for earlier attempts')
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
    for name in ('input.tar.gz','input.tar.gz.run.py','spec.json','generate_scene_presets.py'):
        if not (inp/name).is_file() or not (inp/name).stat().st_size: raise ValueError('Missing or empty input: '+name)
    if not (scripts/'remote.py').is_file(): raise ValueError('Missing remote.py')
    spec=json.loads((inp/'spec.json').read_text())
    for name,key in (('input.tar.gz','bundle_sha256'),('input.tar.gz.run.py','bootstrap_sha256'),('generate_scene_presets.py','cli_sha256')):
        if sha(inp/name)!=spec.get(key): raise ValueError('Input checksum mismatch: '+name)
    if sha(scripts/'remote.py') != spec.get('remote_sha256'):
        raise ValueError('Remote script checksum mismatch')
    duration=spec.get('total_seconds')
    if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0 < duration <= 750:
        raise ValueError('total_seconds must be greater than 0 and at most 750')
    if a.watchdog_seconds < duration+180:
        raise ValueError('watchdog deadline must allow at least 180 seconds beyond remote budget')

def usage_snapshot(name):
    result=call('usage', timeout=90)
    (out/(name+'.txt')).write_text(result.stdout)
    return parse_usage(result.stdout)

def gate(rate):
    estimated=rate*a.watchdog_seconds/3600
    if not math.isfinite(rate) or rate <= 0 or estimated > 3 or estimated > 5:
        raise ValueError(f'Budget gate failed: {rate} CU/hr implies {estimated:.3f} CU by watchdog')
    return estimated

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
    if a.prior_spend_reserve is None:
        raise ValueError('An explicit conservative prior-spend reserve is required')
    if not a.budget_baseline:
        raise ValueError('A before-first-attempt usage snapshot is required for the aggregate cap')
    baseline_path=Path(a.budget_baseline);baseline=parse_usage(baseline_path.read_text())
    if baseline['assignments'] != 0 or baseline['rate'] != 0: raise ValueError('Budget baseline must be idle')
    if not a.rate_evidence:
        raise ValueError('A recorded prior single-L4 usage observation is required')
    evidence=Path(a.rate_evidence); observed=evidence.read_text()
    found=re.search(r'Usage rate:\s*([0-9]+(?:\.[0-9]+)?)/hr\s*Active assignments:\s*1',observed)
    if not found: raise ValueError('Rate evidence must show a single active assignment and rate')
    prior=float(found.group(1)); conservative=prior*2
    before=usage_snapshot('usage-before')
    if before['assignments'] != 0 or before['rate'] != 0: raise ValueError('Existing active assignment; avoid duplicate runtime')
    if before['balance'] < 3: raise ValueError('Account balance below 3 CU target')
    estimated=gate(conservative)
    aggregate=check_aggregate_budget(baseline['balance'],before['balance'],conservative,a.watchdog_seconds,prior_reserve=a.prior_spend_reserve)
    write(out/'cost-gate.json',{'evidence_path':str(evidence.resolve()),'evidence_sha256':sha(evidence),'prior_rate':prior,'conservative_rate':conservative,'watchdog_seconds':a.watchdog_seconds,'max_estimated_cu':estimated,'target_cu':3,'hard_cap_cu':5,'before':before,'baseline':baseline,'baseline_sha256':sha(baseline_path),'aggregate':aggregate,'prior_reserve_assumptions':'Operator supplied conservative upper bound; independently verify the number and limits of earlier attempts','supervisor_sha256':sha(Path(__file__)),'budget_code_sha256':sha(Path(__file__).resolve().parents[3]/'shared/colab_budget.py')})
    status('allocating')
    call('new', '-s', a.session, '--gpu', 'L4', timeout=240)
    status('allocated')
    after=usage_snapshot('usage-allocated')
    if after['assignments'] != 1: raise ValueError('Expected exactly one active assignment')
    gate(after['rate'])
    actual_aggregate=check_aggregate_budget(baseline['balance'],after['balance'],after['rate'],a.watchdog_seconds,prior_reserve=a.prior_spend_reserve)
    write(out/'cost-gate-allocated.json',actual_aggregate)
    inp = Path(a.input_dir); scripts = Path(a.scripts_dir)
    transfer=split_bundle(inp/'input.tar.gz',out/'chunks')
    if transfer['sha256']!=json.loads((inp/'spec.json').read_text())['bundle_sha256']: raise ValueError('Split bundle hash mismatch')
    transfer_path=out/'transfer.json';write(transfer_path,transfer)
    uploads = [(inp/name, name) for name in ('input.tar.gz.run.py','spec.json','generate_scene_presets.py')]
    uploads += [(out/'chunks'/item['name'],item['name']) for item in transfer['chunks']]
    uploads.append((transfer_path,'transfer.json'))
    for local, name in uploads:
        status('uploading', file=name)
        call('upload', '-s', a.session, str(local), '/content/'+name, timeout=240)
    assembly=out/'assemble.py'
    assembly.write_text("""import hashlib,json,pathlib
p=pathlib.Path('/content');m=json.loads((p/'transfer.json').read_text());h=hashlib.sha256()
with (p/'input.tar.gz').open('wb') as target:
 for x in m['chunks']:
  b=(p/x['name']).read_bytes()
  if len(b)!=x['bytes'] or hashlib.sha256(b).hexdigest()!=x['sha256']:raise ValueError('chunk mismatch')
  target.write(b);h.update(b)
if h.hexdigest()!=m['sha256']:raise ValueError('bundle mismatch')
""")
    call('exec','-s',a.session,'--timeout','120','-f',str(assembly),timeout=180)
    status('executing')
    call('exec', '-s', a.session, '--timeout', '850', '-f', str(scripts/'remote.py'), timeout=900)
except BaseException as exc:
    error = f'{type(exc).__name__}: {exc}'; print('ERROR', error, flush=True)
finally:
    # Always try to retrieve even when execution timed out or reported an error.
    status('retrieving', error=error)
    try:
        call('download', '-s', a.session, '/content/procedural-results.json', str(out/'result-metadata.json'), timeout=180)
        meta = json.loads((out/'result-metadata.json').read_text())
        if not meta.get('sha256'): raise RuntimeError('remote archive was not created')
        partial = out/'results.tar.gz.partial'
        call('download', '-s', a.session, '/content/procedural-results.tar.gz', str(partial), timeout=300)
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
    try: usage_snapshot('usage-after')
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError): pass
    status('closed' if stop_ok else 'stop-unconfirmed', error=error, retrieved=retrieved, stop_confirmed=stop_ok)

if error is not None or not stop_ok or not retrieved:
    sys.exit(1)
