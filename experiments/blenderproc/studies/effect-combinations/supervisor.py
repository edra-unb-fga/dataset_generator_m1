"""Run a bounded L4 phase and retrieve it even if the initiating agent disconnects.

Keep this local process (or a detached shell) alive. A separate watchdog attempts
release at the deadline. Network loss and credential revocation can defeat release.
"""
import argparse, fcntl, hashlib, json, os, re, subprocess, sys, tarfile, time
from pathlib import Path

HERE=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def write(path,value):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');os.replace(temp,path)

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_broadcast_failure(archive, matrix, phase):
    """Verify every sealed accepted output in the one known post-render failure."""
    known='operands could not be broadcast together with shapes (640,640,3) (1280,1280,3) '
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive member')
        def read(name):
            member=tar.getmember(name)
            if not member.isfile() or member.size>256*1024*1024:raise ValueError('Unsafe archive member: '+name)
            with tar.extractfile(member) as stream:return stream.read()
        def js(name):return json.loads(read(name))
        if js('definition/realism-phase.json')!=phase:raise ValueError('Archived phase definition differs')
        matrix_bytes=read('definition/realism-matrix.json')
        if hashlib.sha256(matrix_bytes).hexdigest()!=phase['matrix_sha256'] or json.loads(matrix_bytes)!=matrix:
            raise ValueError('Archived matrix differs')
        summary=js('results/summary.json')
        if summary.get('status')!='failed' or summary.get('error')!=known or known not in read('study.log').decode('utf-8'):
            raise ValueError('Failure is not the known resolution-broadcast postprocessing error')
        records=summary.get('records',[])
        if [r.get('cell') for r in records]!=[c['id'] for c in matrix['cells']]:
            raise ValueError('Completed cell list differs from matrix')
        total=0
        for cell,record in zip(matrix['cells'],records):
            prefix='results/cells/'+cell['id']+'/'
            study=js(prefix+'study.json');contract=study['contract']
            runtime={key:study[key] for key in ('config','artwork','grounds','environments')}
            if 'execution_catalog' in study:runtime['execution_catalog']=study['execution_catalog']
            if (fingerprint(contract)!=study['identity'] or fingerprint(study['jobs'])!=contract['jobs_sha256']
                or fingerprint(runtime)!=contract['runtime_sha256']):raise ValueError('Cell study identity mismatch')
            jobs={job['id']:job for job in study['jobs']}
            if len(jobs)!=len(study['jobs']):raise ValueError('Duplicate prepared job')
            selected=cell['jobs'];rows=record.get('rows',[])
            if (record.get('study_identity')!=study['identity'] or record.get('outcome',{}).get('status')!='complete'
                or sorted(record['outcome'].get('selected_jobs',[]))!=sorted(selected)
                or sorted(r['job'] for r in rows)!=sorted(selected)
                or any(r.get('status')!='accepted' for r in rows)):
                raise ValueError('Cell did not complete every declared accepted job')
            execution=js(prefix+'execution.json');selection=execution['selection']
            if execution.get('study_identity')!=study['identity'] or fingerprint({k:v for k,v in selection.items() if k!='identity'})!=selection['identity']:
                raise ValueError('Cell execution identity mismatch')
            for job_id in selected:
                if job_id not in jobs:raise ValueError('Selected job missing from study')
                scene=prefix+'scenes/'+job_id+'/'
                result=js(scene+'result.json')
                if (result.get('status')!='accepted' or result.get('identity')!=study['identity'] or result.get('job')!=jobs[job_id]
                    or result.get('execution',{}).get('selection_identity')!=selection['identity']
                    or set(result.get('files',{}))!={'rgb.png','masks.npz'}):raise ValueError('Incomplete or stale accepted scene')
                for filename,expected in result['files'].items():
                    if hashlib.sha256(read(scene+filename)).hexdigest()!=expected:raise ValueError('Scene file checksum mismatch')
                total+=1
    return {'method':'validated-known-broadcast-failure','original_status':'failed','original_error':known,
            'cells_verified':len(matrix['cells']),'accepted_jobs_verified':total,'source':'verified archive'}


def call(colab,*args,timeout=180,check=True):
    result=subprocess.run([colab,'--auth=oauth2',*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
    print(re.sub(r'(?i)(colab-runtime-proxy-token=)[^\s&]+',r'\1[REDACTED]',result.stdout),flush=True)
    if check and result.returncode:raise RuntimeError(f'{args[0]} exited {result.returncode}')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze');f.add_argument('--output',required=True);f.add_argument('--review',required=True);f.add_argument('--bundle',required=True)
    r=sub.add_parser('run');r.add_argument('--phase',choices=('development','reserved'),required=True);r.add_argument('--output',required=True)
    r.add_argument('--bundle',required=True);r.add_argument('--session',required=True);r.add_argument('--colab',default='colab')
    w=sub.add_parser('watchdog');w.add_argument('--output',required=True);w.add_argument('--session',required=True);w.add_argument('--colab',required=True);w.add_argument('--seconds',type=int,required=True)
    a=p.parse_args();out=Path(a.output).resolve()
    if a.command=='watchdog':
        time.sleep(a.seconds)
        try:
            status=json.loads((out/'status.json').read_text())
            if status.get('stop_confirmed'):return
        except (ValueError,OSError):pass
        for _ in range(3):
            try:
                if call(a.colab,'stop','-s',a.session,timeout=60,check=False).returncode==0:return
            except (OSError,subprocess.TimeoutExpired):pass
            time.sleep(10)
        return
    out.mkdir(parents=True,exist_ok=True)
    if a.command=='freeze':
        review=Path(a.review).resolve();archive=out/'development/results.tar.gz'
        if not review.is_file() or not archive.is_file():raise ValueError('Review file and retrieved development archive are required')
        metadata=json.loads((out/'development/result-metadata.json').read_text())
        if metadata.get('sha256')!=sha(archive) or metadata.get('bytes')!=archive.stat().st_size:raise ValueError('Development archive failed checksum or size verification')
        phase_spec=json.loads((out/'development/phase.json').read_text())
        bundle=Path(a.bundle).resolve();bootstrap=Path(str(bundle)+'.run.py')
        if not bundle.is_file() or not bootstrap.is_file() or sha(bundle)!=phase_spec['bundle_sha256'] or sha(bootstrap)!=phase_spec['bootstrap_sha256']:
            raise ValueError('Development bundle or bootstrap differs from saved phase')
        development=json.loads((HERE/'development-matrix.json').read_text())
        if phase_spec['matrix_sha256']!=sha(HERE/'development-matrix.json'):raise ValueError('Development matrix changed')
        if metadata.get('status')=='complete':recovery=None
        elif metadata.get('status')=='failed':recovery=validate_broadcast_failure(archive,development,phase_spec)
        else:raise ValueError('Unsupported development archive status')
        reserved=json.loads((HERE/'reserved-matrix.json').read_text())
        def treatments(matrix):
            return [({'config':{k:v for k,v in cell.get('config',{}).items() if k not in ('seed','scenes')},
                      'camera_study':cell.get('camera_study'),'treatment':cell.get('treatment')}) for cell in matrix['cells'][:2]]
        if treatments(development)!=treatments(reserved):
            raise ValueError('Reserved treatment must match the frozen development candidate')
        frozen={'bundle_sha256':phase_spec['bundle_sha256'],'development_matrix_sha256':phase_spec['matrix_sha256'],
                'development_sha256':sha(archive),'review_sha256':sha(review),'review_path':str(review),
                'reserved_matrix_sha256':sha(HERE/'reserved-matrix.json'),'frozen_unix':time.time(),
                'development_status':metadata['status'],'recovery_validation':recovery}
        target=out/'freeze.json'
        if target.exists():raise ValueError('Freeze already exists; use a new output root')
        write(target,frozen);print(json.dumps(frozen,indent=2));return
    budget=json.loads((HERE/'budget.json').read_text());duration=budget['watchdog_seconds_per_phase']
    if duration*len(budget['phases'])>budget['max_combined_allocation_seconds']:raise ValueError('Phase budgets exceed combined ceiling')
    matrix=HERE/(a.phase+'-matrix.json');bundle=Path(a.bundle).resolve();bootstrap=Path(str(bundle)+'.run.py')
    if not bundle.is_file() or not bootstrap.is_file():raise ValueError('Input bundle and companion .run.py are required')
    if a.phase=='reserved':
        frozen=json.loads((out/'freeze.json').read_text())
        if frozen['bundle_sha256']!=sha(bundle) or frozen['development_matrix_sha256']!=sha(HERE/'development-matrix.json') or frozen['reserved_matrix_sha256']!=sha(matrix) or frozen['development_sha256']!=sha(out/'development/results.tar.gz') or frozen['review_sha256']!=sha(frozen['review_path']):
            raise ValueError('Frozen development review, archive, or reserved matrix changed')
    with (out/'budget.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger_path=out/'budget-ledger.json'
        ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'schema_version':1,'entries':[]}
        if any(e['phase']==a.phase for e in ledger['entries']):raise ValueError('Phase already reserved; reconcile failures before creating a new study')
        if sum(e['reserved_seconds'] for e in ledger['entries'])+duration>budget['max_combined_allocation_seconds']:raise ValueError('Combined allocation budget exhausted')
        phaseout=out/a.phase;phaseout.mkdir(exist_ok=False)
        entry={'phase':a.phase,'session':a.session,'reserved_seconds':duration,'start_unix':time.time(),'status':'reserved'}
        ledger['entries'].append(entry);write(ledger_path,ledger)
        spec={'phase':a.phase,'bundle_sha256':sha(bundle),'bootstrap_sha256':sha(bootstrap),'matrix_sha256':sha(matrix),
              'remote_seconds':budget['phases'][a.phase]['remote_seconds'],'watchdog_seconds':duration}
        write(phaseout/'phase.json',spec)
        status_path=phaseout/'status.json';write(status_path,{'step':'reserved','stop_confirmed':False})
        with (phaseout/'watchdog.log').open('a') as log:
            subprocess.Popen([sys.executable,__file__,'watchdog','--output',str(phaseout),'--session',a.session,'--colab',a.colab,'--seconds',str(duration)],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        error=None;retrieved=False;stopped=False
        try:
            write(status_path,{'step':'allocating','stop_confirmed':False})
            call(a.colab,'new','-s',a.session,'--gpu','L4',timeout=240)
            for local,remote in [(bundle,'realism-input.tar.gz'),(bootstrap,'realism-input.tar.gz.run.py'),
                                 (matrix,'realism-matrix.json'),(phaseout/'phase.json','realism-phase.json')]:
                call(a.colab,'upload','-s',a.session,str(local),'/content/'+remote,timeout=240)
            write(status_path,{'step':'executing','stop_confirmed':False})
            call(a.colab,'exec','-s',a.session,'--timeout',str(spec['remote_seconds']+90),'-f',str(HERE/'remote.py'),timeout=spec['remote_seconds']+120)
        except BaseException as exc:
            error=f'{type(exc).__name__}: {exc}';print('ERROR',error,flush=True)
        finally:
            write(status_path,{'step':'retrieving','stop_confirmed':False,'error':error})
            try:
                call(a.colab,'download','-s',a.session,'/content/realism-results.json',str(phaseout/'result-metadata.json'),timeout=120)
                meta=json.loads((phaseout/'result-metadata.json').read_text());partial=phaseout/'results.tar.gz.partial'
                if not meta.get('sha256'):raise RuntimeError('No remote result archive')
                call(a.colab,'download','-s',a.session,'/content/realism-results.tar.gz',str(partial),timeout=240)
                if sha(partial)!=meta['sha256'] or partial.stat().st_size!=meta['bytes']:raise RuntimeError('Archive verification failed')
                os.replace(partial,phaseout/'results.tar.gz');retrieved=True
                if meta['status']!='complete':error=error or f"Remote phase {meta['status']}: {meta.get('error')}"
            except BaseException as exc:error=error or f'retrieval {type(exc).__name__}: {exc}'
            for _ in range(3):
                try:
                    if call(a.colab,'stop','-s',a.session,timeout=60,check=False).returncode==0:stopped=True;break
                except (OSError,subprocess.TimeoutExpired):pass
                time.sleep(10)
            entry.update(status='closed' if stopped else 'stop-unconfirmed',retrieved=retrieved,error=error,end_unix=time.time())
            write(ledger_path,ledger);write(status_path,{'step':entry['status'],'stop_confirmed':stopped,'retrieved':retrieved,'error':error})
        if error or not stopped:raise SystemExit(1)

if __name__=='__main__':main()
