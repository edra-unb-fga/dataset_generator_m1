"""Kill outstanding remote process groups then package whatever checkpoints exist."""
import hashlib,json,os,signal,tarfile,time
from pathlib import Path
root=Path('/content/realism-retry');content=Path('/content')
pids=[]
for name in ('retry-child.json','retry-worker.json'):
 try:
  pid=json.loads((content/name).read_text())['pid'];pids.append(pid);os.killpg(pid,signal.SIGTERM)
 except (OSError,ValueError,KeyError):pass
time.sleep(3)
for pid in pids:
 try:os.killpg(pid,signal.SIGKILL)
 except OSError:pass
archive=content/'retry-salvage.tar.gz';tmp=archive.with_suffix('.partial')
with tarfile.open(tmp,'w:gz',compresslevel=1) as tar:
 for p in (root/'handoffs',root/'results/summary.json',root/'results/matrix.json',root/'results/design.json',root/'results/budget.json',root/'workspace/run-config.json',root/'adaptive-policy.json',root/'adaptive-policy.json.basis.json',*root.glob('*.log'),content/'retry-progress.json',content/'retry-worker.log',content/'retry-spec.json',content/'retry-matrix.json',content/'retry-driver.py',content/'retry_config.py'):
  if p.exists():tar.add(p,arcname=('definition/'+p.name if p.parent==content else str(p.relative_to(root))), filter=lambda info: None if info.name.endswith('.partial') else info)
os.replace(tmp,archive)
h=hashlib.sha256()
with archive.open('rb') as f:
 for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
(content/'retry-salvage.json').write_text(json.dumps({'sha256':h.hexdigest(),'bytes':archive.stat().st_size,'kind':'partial; inspect compact handoff manifests','wear_maps_omitted':True}))
print('Salvage archive ready',flush=True)
