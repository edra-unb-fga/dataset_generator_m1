"""Bound Colab CPU 2D phases, preserving 3D reserved budget and verified handoff."""
import argparse, fcntl, hashlib, json, os, re, runpy, subprocess, sys, tarfile, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pathlib import Path

HERE=Path(__file__).resolve().parent
DEFAULT_POLICY=HERE/'colab-supervisor-policy.json'
POLICY_BUNDLE_PATH='experiments/foreground-context/colab-supervisor-policy.json'


class SupervisorPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    schema_version: Literal[1]
    combined_allocation_seconds: int = Field(gt=0)
    phase_allowance_seconds: int = Field(gt=0)
    shutdown_watchdog_seconds: int = Field(gt=0)
    three_d_reserved_seconds: int = Field(gt=0)
    remote_max_seconds: int = Field(gt=0)
    handoff_margin_seconds: int = Field(gt=0)
    remote_min_seconds: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_bounds(self):
        if self.shutdown_watchdog_seconds >= self.phase_allowance_seconds:
            raise ValueError('Watchdog must precede the phase allowance')
        if self.remote_min_seconds > self.remote_max_seconds or self.remote_min_seconds + self.handoff_margin_seconds >= self.shutdown_watchdog_seconds:
            raise ValueError('Remote and handoff bounds do not fit inside watchdog')
        return self


def check_bundle_policy(bundle, policy_bytes):
    with tarfile.open(bundle,'r:gz') as tar:
        member=tar.getmember(POLICY_BUNDLE_PATH)
        if not member.isfile() or tar.extractfile(member).read() != policy_bytes:
            raise ValueError('Supervisor policy does not match immutable bundle')


# Shared transport only: each study retains its own budget and lifecycle policy.
_transport = runpy.run_path(str(HERE.parent / 'shared/colab_transport.py'))
sha, write, call = (_transport[name] for name in ('sha', 'write', 'call'))


def closed_seconds(entry):
    if entry.get('status')!='closed' or 'end_unix' not in entry or entry['end_unix'] < entry['start_unix']:
        raise ValueError('An allocation is active or has unconfirmed shutdown; reconcile before continuing')
    return entry['end_unix']-entry['start_unix']


def budget_check(three_d, two_d, phase, policy, *, retry_failed_development=False):
    three=sum(closed_seconds(e) for e in three_d['entries'])
    two=sum(closed_seconds(e) for e in two_d['entries'])
    previous=[e for e in two_d['entries'] if e['phase']==phase]
    if retry_failed_development:
        if (phase != 'development' or len(previous) != 1 or previous[0].get('retrieved') is not False
                or not str(previous[0].get('error', '')).startswith('RuntimeError: upload exited')):
            raise ValueError('Retry requires one closed, unretrieved development upload failure')
    elif previous:raise ValueError('Phase already attempted')
    remaining_3d=0 if any(e['phase']=='reserved' for e in three_d['entries']) else policy.three_d_reserved_seconds
    remaining_2d=policy.phase_allowance_seconds*(2 if phase=='development' else 1)
    needed=three+two+remaining_3d+remaining_2d
    if needed>policy.combined_allocation_seconds:raise ValueError('Combined Colab budget insufficient')
    return {'three_d_actual_seconds':three,'two_d_actual_seconds':two,'three_d_reserved_seconds':remaining_3d,
            'planned_two_d_seconds':remaining_2d,'max_combined_allocation_seconds':policy.combined_allocation_seconds,'conservative_total_seconds':needed}


def remote_budget(elapsed, policy):
    # Preserve 210 seconds for phase upload, handoff, and timeout overhead.
    remaining=min(policy.remote_max_seconds, policy.shutdown_watchdog_seconds - elapsed - policy.handoff_margin_seconds)
    if remaining < policy.remote_min_seconds:raise TimeoutError('Insufficient watchdog time for a study and handoff')
    return int(remaining)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    freeze=sub.add_parser('freeze');freeze.add_argument('--output',required=True);freeze.add_argument('--review',required=True)
    run=sub.add_parser('run');run.add_argument('--phase',choices=('development','reserved'),required=True)
    run.add_argument('--output',required=True);run.add_argument('--three-d-root',required=True);run.add_argument('--bundle',required=True)
    run.add_argument('--session',required=True);run.add_argument('--colab',default='colab');run.add_argument('--policy',default=DEFAULT_POLICY)
    run.add_argument('--retry-failed-development',action='store_true',help='Explicitly retry one closed failed development upload')
    watchdog=sub.add_parser('watchdog');watchdog.add_argument('--output',required=True);watchdog.add_argument('--session',required=True)
    watchdog.add_argument('--colab',required=True);watchdog.add_argument('--seconds',type=int,required=True)
    args=parser.parse_args();root=Path(args.output).resolve()
    if args.command=='watchdog':
        time.sleep(args.seconds)
        try:
            if json.loads((root/'status.json').read_text()).get('stop_confirmed'):return
        except (OSError,ValueError):pass
        for _ in range(3):
            try:
                if call(args.colab,'stop','-s',args.session,timeout=60,check=False).returncode==0:return
            except (OSError,subprocess.TimeoutExpired):pass
            time.sleep(10)
        return
    if args.command=='freeze':
        review=Path(args.review).resolve()
        selection=root/'development-selection.json'
        dev=root/(json.loads(selection.read_text())['attempt_directory'] if selection.exists() else 'development')
        archive=dev/'results.tar.gz'
        meta=json.loads((dev/'result-metadata.json').read_text());spec=json.loads((dev/'phase.json').read_text())
        if meta.get('status')!='complete' or sha(archive)!=meta.get('sha256') or not review.is_file():raise ValueError('Verified complete development and review required')
        target=root/'freeze.json'
        if target.exists():raise ValueError('Already frozen')
        write(target,{'review':str(review),'review_sha256':sha(review),'development_sha256':sha(archive),
                      'development_attempt':dev.name,
                      'bundle_sha256':spec['bundle_sha256'], 'supervisor_policy_sha256':spec['supervisor_policy_sha256']})
        return
    bundle=Path(args.bundle).resolve();three_root=Path(args.three_d_root).resolve()
    if not bundle.is_file() or not (three_root/'budget-ledger.json').is_file():raise ValueError('Bundle and 3D budget ledger required')
    policy_bytes=Path(args.policy).read_bytes();policy=SupervisorPolicy.model_validate_json(policy_bytes)
    check_bundle_policy(bundle,policy_bytes)
    root.mkdir(parents=True,exist_ok=True)
    with (three_root/'budget.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        three=json.loads((three_root/'budget-ledger.json').read_text())
        if not any(e.get('phase') == 'reserved' and e.get('status') == 'closed' for e in three['entries']):
            raise ValueError('The 3D reserved phase must be closed before allocating a 2D runtime')
        ledger_path=root/'budget-ledger.json';ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'schema_version':1,'entries':[]}
        basis=budget_check(three,ledger,args.phase,policy,retry_failed_development=args.retry_failed_development)
        if args.retry_failed_development:
            prior=json.loads((root/'development/status.json').read_text())
            if not prior.get('stop_confirmed') or (root/'freeze.json').exists():
                raise ValueError('Retry requires confirmed shutdown and an unfrozen study')
            previous_spec=json.loads((root/'development/phase.json').read_text())
            if (previous_spec['bundle_sha256']!=sha(bundle) or
                    previous_spec['supervisor_policy_sha256']!=hashlib.sha256(policy_bytes).hexdigest()):
                raise ValueError('Retry must use the original immutable bundle and supervisor policy')
        if args.phase=='reserved':
            frozen=json.loads((root/'freeze.json').read_text())
            if frozen['bundle_sha256']!=sha(bundle) or frozen['supervisor_policy_sha256']!=hashlib.sha256(policy_bytes).hexdigest() or frozen['development_sha256']!=sha(root/frozen.get('development_attempt','development')/'results.tar.gz') or frozen['review_sha256']!=sha(frozen['review']):
                raise ValueError('Frozen review, development evidence, or bundle changed')
        out=root/('development-retry-01' if args.retry_failed_development else args.phase);out.mkdir(exist_ok=False)
        write(out/'budget-basis.json',basis)
        remote=out/'remote.py';remote.write_bytes((HERE/'colab_remote.py').read_bytes())
        chunk_helper=out/'context_chunking.py';chunk_helper.write_bytes((HERE.parent/'shared/colab_transport.py').read_bytes())
        chunks=runpy.run_path(str(chunk_helper))['split_bundle'](bundle,out/'chunks')
        if chunks['sha256']!=sha(bundle):raise ValueError('Split bundle checksum mismatch')
        (out/'supervisor-policy.json').write_bytes(policy_bytes)
        spec={'phase':args.phase,'samples':20 if args.phase=='development' else 12,'bundle_sha256':sha(bundle),
              'remote_sha256':sha(remote),'watchdog_seconds':policy.shutdown_watchdog_seconds,
              'chunk_helper_sha256':sha(chunk_helper),'transfer':chunks,
              'supervisor_policy_sha256':hashlib.sha256(policy_bytes).hexdigest(), 'supervisor_policy':policy.model_dump(mode='json')}
        write(out/'phase.json',spec);status=out/'status.json';write(status,{'step':'reserved','stop_confirmed':False})
        entry={'phase':args.phase,'attempt_directory':out.name,'retry_failed_development':args.retry_failed_development,
               'session':args.session,'reserved_seconds':policy.phase_allowance_seconds,'start_unix':time.time(),'status':'reserved'}
        ledger['entries'].append(entry);write(ledger_path,ledger)
        with (out/'watchdog.log').open('a') as log:
            subprocess.Popen([sys.executable,__file__,'watchdog','--output',str(out),'--session',args.session,'--colab',args.colab,'--seconds',str(policy.shutdown_watchdog_seconds)],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        error=None;retrieved=False;stopped=False
        try:
            write(status,{'step':'allocating','stop_confirmed':False})
            call(args.colab,'new','-s',args.session,timeout=180)
            call(args.colab,'upload','-s',args.session,str(chunk_helper),'/content/context_chunking.py',timeout=60)
            for chunk in chunks['chunks']:
                remote_budget(time.time()-entry['start_unix'],policy)
                call(args.colab,'upload','-s',args.session,str(out/'chunks'/chunk['name']),'/content/'+chunk['name'],timeout=120)
            spec['remote_seconds']=remote_budget(time.time()-entry['start_unix'],policy)
            write(out/'phase.json',spec)
            call(args.colab,'upload','-s',args.session,str(out/'phase.json'),'/content/context-phase.json',timeout=60)
            write(status,{'step':'executing','stop_confirmed':False})
            call(args.colab,'exec','-s',args.session,'--timeout',str(spec['remote_seconds']+15),'-f',str(remote),timeout=spec['remote_seconds']+30)
        except BaseException as exc:error=f'{type(exc).__name__}: {exc}'
        finally:
            write(status,{'step':'retrieving','stop_confirmed':False,'error':error})
            try:
                call(args.colab,'download','-s',args.session,'/content/context-results.json',str(out/'result-metadata.json'),timeout=60)
                meta=json.loads((out/'result-metadata.json').read_text());partial=out/'results.tar.gz.partial'
                call(args.colab,'download','-s',args.session,'/content/context-results.tar.gz',str(partial),timeout=120)
                if sha(partial)!=meta['sha256'] or partial.stat().st_size!=meta['bytes']:raise ValueError('Result checksum mismatch')
                os.replace(partial,out/'results.tar.gz');retrieved=True
                if meta['status']!='complete':error=error or f"Remote phase {meta['status']}: {meta.get('error')}"
            except BaseException as exc:error=error or f'Retrieval {type(exc).__name__}: {exc}'
            for _ in range(3):
                try:
                    if call(args.colab,'stop','-s',args.session,timeout=60,check=False).returncode==0:stopped=True;break
                except (OSError,subprocess.TimeoutExpired):pass
                time.sleep(10)
            entry.update(status='closed' if stopped else 'stop-unconfirmed',end_unix=time.time(),retrieved=retrieved,error=error)
            write(ledger_path,ledger);write(status,{'step':entry['status'],'stop_confirmed':stopped,'retrieved':retrieved,'error':error})
            if args.phase=='development' and retrieved and stopped and not error:
                write(root/'development-selection.json',{'attempt_directory':out.name,'bundle_sha256':spec['bundle_sha256']})
        if error or not stopped:raise SystemExit(1)

if __name__=='__main__':main()
