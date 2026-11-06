"""Verify original and recovered study evidence and build a separate review gallery."""
import argparse, hashlib, importlib.util, json, shutil, tarfile, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ORIGINAL = ROOT/'outputs/experiments/balanced-relocated-partial'
BUNDLE = 'aced5844c1a37b545a2bd4d0dec061d97d49382fa1695c12dc6ac953afd276a3'
ARCHIVE = '323c69c48c70b0f4729ff2d9452ae2a5a0e11527e8bc98577f6c3c8a1c8bd2d9'
IDENTITIES = {'candidate-0':'9fdbeca454f5dd13e06b21166d3a985d1de475cd5dbd8714e00f6172d957b5b2', 'candidate-1':'845dc41c3bea849d7fc7ec41e4dfd3ea95e2e303326960cb445d6f7894a11b1c'}

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def read(p):return json.loads(p.read_text())
def study(path):
 s=read(path/'study.json'); runtime={k:s[k] for k in ('config','artwork','grounds','environments','execution_catalog')}
 if digest(s['contract'])!=s['identity'] or digest(s['jobs'])!=s['contract']['jobs_sha256'] or digest(runtime)!=s['contract']['runtime_sha256']:raise ValueError('Changed study contract: '+str(path))
 return s

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--completion',type=Path,help='Controller output containing status.json, result-metadata.json, results.tar.gz');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('Output must be a fresh directory')
 if sha(ORIGINAL/'input-bundle.tar.gz')!=BUNDLE or sha(ORIGINAL/'results.tar.gz')!=ARCHIVE:raise ValueError('Original bundle or archive checksum mismatch')
 originals={k:study(ORIGINAL/'results'/k) for k in IDENTITIES}
 for k,s in originals.items():
  if s['identity']!=IDENTITIES[k]:raise ValueError('Original identity mismatch')
 base=originals['candidate-1']; c=base['config']
 if (c['seed'],c['scene_offset'],c['scenes'])!=(20261026,100,100):raise ValueError('Unexpected original plan')
 status={'original_archive_sha256':ARCHIVE,'bundle_sha256':BUNDLE,'completion':'not supplied','heldout_reference_pool':'reused original reference pool','counts':{},'warnings':[]}
 rows=[]; seen=set()
 with tempfile.TemporaryDirectory(prefix='balanced-review-') as tmp:
  extract=Path(tmp); completion=None; meta=None
  if a.completion:
   controller=read(a.completion/'status.json');meta=read(a.completion/'result-metadata.json');archive=a.completion/'results.tar.gz'
   if not controller.get('retrieved') or not archive.is_file():raise ValueError('Completion archive was not confirmed retrieved')
   if sha(archive)!=meta.get('sha256') or archive.stat().st_size!=meta.get('bytes'):raise ValueError('Completion archive hash or size mismatch')
   if meta.get('status') not in ('complete','failed'):raise ValueError('Unknown remote status')
   status.update(completion=meta['status'],completion_archive_sha256=meta['sha256'],controller=controller,remote_error=meta.get('error'))
   if not controller.get('stop_confirmed'):status['warnings'].append('Runtime stop was not confirmed.')
   if controller.get('error'):status['warnings'].append('Controller error: '+str(controller['error']))
   if meta['status']!='complete':status['warnings'].append('Remote reported failure: '+str(meta.get('error')))
   with tarfile.open(archive,'r:gz') as t:
    for member in t.getmembers():
     if not (member.isfile() or member.isdir()) or member.name.startswith('/') or '..' in Path(member.name).parts:raise ValueError('Unsafe archive member')
    t.extractall(extract,filter='data')
   spec=read(extract/'spec.json')
   if spec.get('bundle_sha256')!=BUNDLE or spec.get('policy_sha256')!='4505f03ffc6ccefcf07646b0264308838fa53e10e2bd3990972b7401beaec83f' or spec.get('candidate1_identity')!=IDENTITIES['candidate-1'] or spec.get('remote_sha256')!=sha(Path(__file__).with_name('remote.py')) or spec.get('original_study_sha256')!='76279e80f3d7a4a1170baba9221c1d1922d729a172bf3e9305049acc3dc75d6f':raise ValueError('Completion source or input spec mismatch')
   if sha(extract/'original-study.json')!=spec['original_study_sha256'] or read(extract/'original-study.json')!=base:raise ValueError('Archived original study differs')
   old=read(ORIGINAL/'policy.json');fresh=read(extract/'fresh-policy.json');actual=read(extract/'policy.json')
   if {k:v for k,v in old.items() if k!='guards'}!={k:v for k,v in fresh.items() if k!='guards'} or {k:v for k,v in old.items() if k!='guards'}!={k:v for k,v in actual.items() if k!='guards'}:raise ValueError('Execution profile changed')
   expected_guards={k:max(old['guards'][k],fresh['guards'][k]) for k in ('min_available_gib','min_gpu_free_mib')}
   expected_guards.update({k:min(old['guards'][k],fresh['guards'][k]) for k in ('rss_limit_gib','max_swap_out_mib','probe_timeout_seconds')})
   if actual['guards']!=expected_guards or set(old['guards'])!=set(expected_guards) or set(fresh['guards'])!=set(expected_guards):raise ValueError('Resource guard mismatch')
   completion=extract/'results'
  def add(label,path,s,allowed,origin):
   by_id={j['id']:j for j in s['jobs']}
   if len(by_id)!=len(s['jobs']):raise ValueError('Duplicate planned IDs')
   scene_root=path/'scenes'
   if not scene_root.exists():return
   dirs={x.name for x in scene_root.iterdir() if x.is_dir() and (x/'result.json').exists()}
   if not dirs<=allowed or not dirs<=set(by_id):raise ValueError('Unexpected or duplicate scene in '+label)
   execution=read(path/'execution.json') if dirs else None
   if execution:
    sel=execution['selection']; sid=sel['identity']
    if execution['study_identity']!=s['identity'] or digest({k:v for k,v in sel.items() if k!='identity'})!=sid:raise ValueError('Execution fingerprint mismatch')
   for job_id in sorted(dirs):
    key=(label,job_id)
    if key in seen:raise ValueError('Duplicate scene '+str(key))
    d=scene_root/job_id;r=read(d/'result.json');job=by_id[job_id]
    if r.get('identity')!=s['identity'] or r.get('job')!=job:raise ValueError('Scene identity mismatch '+str(d))
    if r.get('status')=='rejected':status['warnings'].append(f'{label} {job_id} rejected');continue
    if r.get('status')!='accepted' or set(r.get('files',{}))!={'rgb.png','masks.npz'}:raise ValueError('Invalid accepted files '+str(d))
    if any(sha(d/f)!=h for f,h in r['files'].items()):raise ValueError('Scene file checksum mismatch '+str(d))
    if r.get('execution',{}).get('selection_identity')!=sid:raise ValueError('Scene execution mismatch')
    seen.add(key);name=f'{label}-{job_id}.png'
    rows.append((d/'rgb.png',{'path':'images/'+name,'engine':'BlenderProc 3D','family':origin,'condition':job.get('environment_geometry','unknown'),'label':f'{label} · {job_id}', 'metadata':{'source':origin,'study_identity':s['identity'],'job':job,'result':r,'heldout_reference_pool':'reused original reference pool' if label=='heldout' else None}}))
  expected_files={}
  for label,n in [('candidate-0',100),('candidate-1',69)]:
   for i in range(n):
    d=ORIGINAL/'results'/label/'scenes'/f'{i:03d}-base-fast'
    for name in ('result.json','rgb.png','masks.npz'):
     expected_files[f'results/{label}/scenes/{d.name}/{name}']=sha(d/name)
  verified=set()
  with tarfile.open(ORIGINAL/'results.tar.gz','r|gz') as tar:
   for member in tar:
    if member.name in expected_files:
     if member.name in verified or not member.isfile():raise ValueError('Invalid original archive member')
     f=tar.extractfile(member)
     if f is None or hashlib.sha256(f.read()).hexdigest()!=expected_files[member.name]:raise ValueError('Original evidence differs from archive: '+member.name)
     verified.add(member.name)
  if verified!=set(expected_files):raise ValueError('Original archive missing expected evidence')
  for label,n in [('candidate-0',100),('candidate-1',69)]:
   add(label,ORIGINAL/'results'/label,originals[label],{f'{i:03d}-base-fast' for i in range(n)},'Original candidate')
  if completion and completion.exists():
   for label in ('candidate-1','heldout'):
    path=completion/label
    if not (path/'study.json').exists():continue
    s=study(path)
    if label=='candidate-1':
     if s['jobs']!=base['jobs'] or {k:v for k,v in s['contract'].items() if k!='runtime_sha256'}!={k:v for k,v in base['contract'].items() if k!='runtime_sha256'}:raise ValueError('Completion candidate scene contract differs')
     if {k:v for k,v in s['execution_catalog'].items() if k!='guards'}!={k:v for k,v in base['execution_catalog'].items() if k!='guards'} or s['execution_catalog']['guards']!=expected_guards:raise ValueError('Unexpected candidate execution catalog')
     status['completion_candidate_identity']=s['identity']
     allowed={f'{i:03d}-base-fast' for i in range(69,100)};origin='Recovered candidate'
    else:
     cfg=s['config'];original_cfg=base['config']; changing={'seed','scene_offset','scenes'}
     if (cfg['seed'],cfg['scene_offset'],cfg['scenes'])!=(20261117,0,20) or {k:v for k,v in cfg.items() if k not in changing}!={k:v for k,v in original_cfg.items() if k not in changing}:raise ValueError('Held-out config differs')
     for k in ('harness_sources','harness_source_sha256','renderer_script_sha256','reference','assets','artwork'):
      if s['contract'][k]!=base['contract'][k]:raise ValueError('Held-out source/input differs: '+k)
     allowed={f'{i:03d}-base-fast' for i in range(20)};origin='Held-out seed · reused reference pool'
    add(label,path,s,allowed,origin)
  for label in ('candidate-0','candidate-1','heldout'):status['counts'][label]=sum(k[0]==label for k in seen)
  full_counts=status['counts']=={'candidate-0':100,'candidate-1':100,'heldout':20}
  complete=full_counts and bool(meta) and meta['status']=='complete'
  if meta and meta['status']=='complete' and not full_counts:raise ValueError('Remote claims complete but accepted scenes are missing')
  status['complete']=complete
  if not complete:status['warnings'].append('Partial or failed study: inspect remote status and compare counts with the planned 200 + 20.')
  a.output.mkdir(parents=True);(a.output/'images').mkdir()
  for source,item in rows:shutil.copyfile(source,a.output/item['path'])
  title=('Complete' if complete else 'PARTIAL')+' balanced 3D review — held-out seed reuses reference pool'
  manifest={'title':title,'status':status,'images':[item for _,item in rows]}
  (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
  (a.output/'verification.json').write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n')
  spec=importlib.util.spec_from_file_location('review_builder',ROOT/'scripts/build_scene_review_gallery.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder);builder.build(a.output/'manifest.json',a.output/'index.html')
  print(json.dumps(status,indent=2))
if __name__=='__main__':main()
