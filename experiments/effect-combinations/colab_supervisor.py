"""Self-contained bounded Colab CPU study; retrieve evidence and stop on every exit."""
import argparse, hashlib, json, os, re, runpy, subprocess, sys, tarfile, time
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

HERE=Path(__file__).resolve().parent
class Policy(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    schema_version: Literal[1]
    allocation_timeout_seconds: int = Field(ge=300, le=1800)
    remote_max_seconds: int = Field(ge=120)
    remote_min_seconds: int = Field(ge=60)
    handoff_margin_seconds: int = Field(ge=90)
    samples: int = Field(ge=1, le=20)
    @model_validator(mode='after')
    def bounds(self):
        if self.remote_min_seconds > self.remote_max_seconds or self.remote_max_seconds + self.handoff_margin_seconds > self.allocation_timeout_seconds:
            raise ValueError('Remote and handoff must fit allocation')
        return self

# Shared transport only: each study retains its own budget and lifecycle policy.
_transport = runpy.run_path(str(HERE.parent / 'shared/colab_transport.py'))
sha, write, call = (_transport[name] for name in ('sha', 'write', 'call'))


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    run=sub.add_parser('run');run.add_argument('--bundle',required=True);run.add_argument('--output',required=True);run.add_argument('--session',required=True)
    run.add_argument('--phase',choices=['development','reserved'],default='development');run.add_argument('--colab',default='colab');run.add_argument('--policy',default=str(HERE/'colab-supervisor-policy.json'))
    watchdog=sub.add_parser('watchdog');watchdog.add_argument('--output',required=True);watchdog.add_argument('--session',required=True);watchdog.add_argument('--colab',required=True);watchdog.add_argument('--seconds',type=int,required=True)
    args=p.parse_args();root=Path(args.output).resolve()
    if args.action=='watchdog':
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
    bundle=Path(args.bundle).resolve(); policy_bytes=Path(args.policy).read_bytes(); policy=Policy.model_validate_json(policy_bytes)
    with tarfile.open(bundle,'r:gz') as tar:
        member=tar.getmember('experiments/effect-combinations/colab-supervisor-policy.json')
        if not member.isfile() or tar.extractfile(member).read()!=policy_bytes:raise ValueError('Bundle policy differs from supervisor policy')
    root.mkdir(parents=True,exist_ok=False)
    remote=root/'remote.py';remote.write_bytes((HERE/'colab_remote.py').read_bytes())
    chunk_helper=root/'context_chunking.py';chunk_helper.write_bytes((HERE.parent/'shared/colab_transport.py').read_bytes())
    chunks=runpy.run_path(str(chunk_helper))['split_bundle'](bundle,root/'chunks')
    if chunks['sha256']!=sha(bundle):raise ValueError('Split bundle checksum mismatch')
    (root/'supervisor-policy.json').write_bytes(policy_bytes)
    started=time.time();spec={'phase':args.phase,'samples':policy.samples,'bundle_sha256':sha(bundle),
        'remote_sha256':sha(remote),'chunk_helper_sha256':sha(chunk_helper),'transfer':chunks,
        'supervisor_policy_sha256':hashlib.sha256(policy_bytes).hexdigest(),'supervisor_policy':policy.model_dump(mode='json')}
    write(root/'phase.json',spec);write(root/'status.json',{'step':'allocating','stop_confirmed':False,'started_unix':started})
    with (root/'watchdog.log').open('a') as log:
        subprocess.Popen([sys.executable,__file__,'watchdog','--output',str(root),'--session',args.session,'--colab',args.colab,'--seconds',str(policy.allocation_timeout_seconds)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    error=None;retrieved=False;stopped=False
    try:
        call(args.colab,'new','-s',args.session,timeout=180)
        usage=call(args.colab,'usage',timeout=60,check=False)
        (root/'usage-on-allocation.txt').write_text(re.sub(r'(?i)(colab-runtime-proxy-token=)[^\s&]+',r'\1[REDACTED]',usage.stdout),encoding='utf-8')
        call(args.colab,'upload','-s',args.session,str(chunk_helper),'/content/context_chunking.py',timeout=60)
        for chunk in chunks['chunks']:
            if time.time()-started+policy.handoff_margin_seconds+policy.remote_min_seconds>=policy.allocation_timeout_seconds:raise TimeoutError('Insufficient time remaining before allocation deadline')
            call(args.colab,'upload','-s',args.session,str(root/'chunks'/chunk['name']),'/content/'+chunk['name'],timeout=120)
        spec['remote_seconds']=int(min(policy.remote_max_seconds,policy.allocation_timeout_seconds-(time.time()-started)-policy.handoff_margin_seconds))
        if spec['remote_seconds']<policy.remote_min_seconds:raise TimeoutError('Insufficient study time')
        write(root/'phase.json',spec);call(args.colab,'upload','-s',args.session,str(root/'phase.json'),'/content/context-phase.json',timeout=60)
        write(root/'status.json',{'step':'executing','stop_confirmed':False,'started_unix':started,'remote_seconds':spec['remote_seconds']})
        # One blocking call, no polling of a stable runtime. Remote packages evidence in finally.
        call(args.colab,'exec','-s',args.session,'--timeout',str(spec['remote_seconds']+15),'-f',str(remote),timeout=spec['remote_seconds']+30)
    except BaseException as exc:error=f'{type(exc).__name__}: {exc}'
    finally:
        write(root/'status.json',{'step':'retrieving','stop_confirmed':False,'started_unix':started,'error':error})
        try:
            call(args.colab,'download','-s',args.session,'/content/context-results.json',str(root/'result-metadata.json'),timeout=60)
            meta=json.loads((root/'result-metadata.json').read_text());partial=root/'results.tar.gz.partial'
            call(args.colab,'download','-s',args.session,'/content/context-results.tar.gz',str(partial),timeout=120)
            if sha(partial)!=meta['sha256'] or partial.stat().st_size!=meta['bytes']:raise ValueError('Result checksum mismatch')
            os.replace(partial,root/'results.tar.gz');retrieved=True
            if meta['status']!='complete':error=error or f"Remote phase {meta['status']}: {meta.get('error')}"
        except BaseException as exc:error=error or f'Retrieval {type(exc).__name__}: {exc}'
        for _ in range(3):
            try:
                if call(args.colab,'stop','-s',args.session,timeout=60,check=False).returncode==0:stopped=True;break
            except (OSError,subprocess.TimeoutExpired):pass
            time.sleep(10)
        write(root/'status.json',{'step':'closed' if stopped else 'stop-unconfirmed','stop_confirmed':stopped,'retrieved':retrieved,'error':error,'started_unix':started,'ended_unix':time.time()})
        if error or not stopped:raise SystemExit(1)
if __name__=='__main__':main()
