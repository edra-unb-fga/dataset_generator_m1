"""Detached bounded retry: independent watchdog, remote checkpoints, salvage then stop."""
import argparse,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def write(p,v):
 p=Path(p);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');os.replace(tmp,p)
def call(colab,*args,timeout=120,check=True):
 r=subprocess.run([colab,'--auth=oauth2',*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
 print(re.sub(r'(?i)(colab-runtime-proxy-token=)[^\s&]+',r'\1[REDACTED]',r.stdout),flush=True)
 if check and r.returncode:raise RuntimeError(f'{args[0]} exited {r.returncode}')
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--bundle');p.add_argument('--output',required=True);p.add_argument('--session',required=True);p.add_argument('--colab',default='colab');p.add_argument('--watchdog',action='store_true');p.add_argument('--seconds',type=int,default=1200);a=p.parse_args()
 out=Path(a.output).resolve()
 if a.watchdog:
  time.sleep(a.seconds)
  try:
   if json.loads((out/'status.json').read_text()).get('stop_confirmed'):return
  except (OSError,ValueError):pass
  for _ in range(3):
   try:
    if call(a.colab,'stop','-s',a.session,timeout=45,check=False).returncode==0:return
   except (OSError,subprocess.TimeoutExpired):pass
   time.sleep(10)
  return
 if not a.bundle:raise ValueError('Bundle required')
 bundle=Path(a.bundle).resolve();bootstrap=Path(str(bundle)+'.run.py');matrix=HERE/'development-matrix.json';driver=HERE/'compact-driver.py'
 if not all(p.is_file() for p in (bundle,bootstrap,matrix,driver)):raise ValueError('Missing study input')
 if out.exists():raise ValueError('Use a new output folder; do not overwrite prior evidence')
 out.mkdir(parents=True);start=time.monotonic();stop=False;retrieved=False;error=None
 spec={'schema_version':1,'bundle_sha256':sha(bundle),'bootstrap_sha256':sha(bootstrap),'matrix_sha256':sha(matrix),'driver_sha256':sha(driver),'config_helper_sha256':sha(HERE/'retry_config.py'),'remote_seconds':780,'watchdog_seconds':a.seconds,'poll_seconds':300}
 if a.seconds<1140:raise ValueError('Watchdog must allow three 300 second polls and retrieval')
 write(out/'spec.json',spec);write(out/'status.json',{'step':'reserved','stop_confirmed':False})
 with (out/'watchdog.log').open('a') as log:
  subprocess.Popen([sys.executable,__file__,'--watchdog','--seconds',str(a.seconds),'--output',str(out),'--session',a.session,'--colab',a.colab],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
 try:
  write(out/'status.json',{'step':'allocating','stop_confirmed':False})
  call(a.colab,'new','-s',a.session,'--gpu','L4',timeout=180)
  for path,name in [(bundle,'retry-input.tar.gz'),(bootstrap,'retry-input.tar.gz.run.py'),(matrix,'retry-matrix.json'),(driver,'retry-driver.py'),(HERE/'worker.py','retry-worker.py'),(HERE/'retry_config.py','retry_config.py'),(out/'spec.json','retry-spec.json')]:
   call(a.colab,'upload','-s',a.session,path,'/content/'+name,timeout=180)
  call(a.colab,'exec','-s',a.session,'--timeout','60','-f',HERE/'launcher.py',timeout=80)
  write(out/'status.json',{'step':'running','stop_confirmed':False})
  for _ in range(3):
   if time.monotonic()-start+300> a.seconds-120:break
   time.sleep(300)
   probe=call(a.colab,'download','-s',a.session,'/content/retry-results.json',out/'result.json',timeout=60,check=False)
   if probe.returncode==0 and (out/'result.json').exists():break
  if (out/'result.json').exists():
   meta=json.loads((out/'result.json').read_text());partial=out/'results.tar.gz.partial'
   call(a.colab,'download','-s',a.session,'/content/retry-results.tar.gz',partial,timeout=120)
   if partial.stat().st_size!=meta['bytes'] or sha(partial)!=meta['sha256']:raise ValueError('Final archive integrity mismatch')
   os.replace(partial,out/'results.tar.gz');retrieved=True
   if meta['status']!='complete':error='Remote worker failed: '+str(meta.get('error'))
  else:error='Final metadata unavailable before salvage deadline'
 except BaseException as exc:error=error or f'{type(exc).__name__}: {exc}'
 finally:
  if not retrieved:
   write(out/'status.json',{'step':'salvaging','error':error,'stop_confirmed':False})
   try:
    call(a.colab,'exec','-s',a.session,'--timeout','75','-f',HERE/'salvage.py',timeout=90)
    call(a.colab,'download','-s',a.session,'/content/retry-salvage.json',out/'salvage.json',timeout=60)
    meta=json.loads((out/'salvage.json').read_text());partial=out/'salvage.tar.gz.partial'
    call(a.colab,'download','-s',a.session,'/content/retry-salvage.tar.gz',partial,timeout=90)
    if partial.stat().st_size!=meta['bytes'] or sha(partial)!=meta['sha256']:raise ValueError('Salvage integrity mismatch')
    os.replace(partial,out/'salvage.tar.gz');retrieved=True
   except BaseException as exc:error=(error or '')+'; salvage '+f'{type(exc).__name__}: {exc}'
  for _ in range(3):
   try:
    if call(a.colab,'stop','-s',a.session,timeout=45,check=False).returncode==0:stop=True;break
   except (OSError,subprocess.TimeoutExpired):pass
   time.sleep(10)
  write(out/'status.json',{'step':'closed' if stop else 'stop-unconfirmed','stop_confirmed':stop,'retrieved':retrieved,'error':error,'elapsed_seconds':time.monotonic()-start})
 if error or not stop:raise SystemExit(1)
if __name__=='__main__':main()
