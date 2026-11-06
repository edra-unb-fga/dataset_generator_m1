"""Stage the sealed original and verify accepted IDs before any allocation."""
import hashlib,json,shutil,sys
from pathlib import Path
root=Path(__file__).resolve().parents[4]
partial=root/'outputs/experiments/balanced-relocated-partial'
other=root/'outputs/experiments/paired-lighting-run/input'
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
expected={'input-bundle.tar.gz':'aced5844c1a37b545a2bd4d0dec061d97d49382fa1695c12dc6ac953afd276a3','results.tar.gz':'323c69c48c70b0f4729ff2d9452ae2a5a0e11527e8bc98577f6c3c8a1c8bd2d9','policy.json':'4505f03ffc6ccefcf07646b0264308838fa53e10e2bd3990972b7401beaec83f'}
for f,h in expected.items():
 if sha(partial/f)!=h:raise ValueError(f+' checksum mismatch')
identity='845dc41c3bea849d7fc7ec41e4dfd3ea95e2e303326960cb445d6f7894a11b1c'
for label,expected_count in [('candidate-0',100),('candidate-1',69)]:
 p=partial/'results'/label;s=json.loads((p/'study.json').read_text())
 if digest(s['contract'])!=s['identity'] or digest(s['jobs'])!=s['contract']['jobs_sha256']:raise ValueError('Study contract invalid')
 if label=='candidate-1' and s['identity']!=identity:raise ValueError('Original identity changed')
 rows=[]
 for j in s['jobs']:
  d=p/'scenes'/j['id']; f=d/'result.json'
  if not f.exists():continue
  r=json.loads(f.read_text())
  if r['status']!='accepted' or r['identity']!=s['identity'] or r['job']!=j or set(r['files'])!={'rgb.png','masks.npz'}:raise ValueError('Invalid accepted result')
  if any(sha(d/name)!=h for name,h in r['files'].items()):raise ValueError('Scene hash mismatch')
  rows.append(j['id'])
 if rows!=[f'{i:03d}-base-fast' for i in range(expected_count)]:raise ValueError('Accepted IDs differ from expected')
for source,name in [(partial/'input-bundle.tar.gz','input.tar.gz'),(partial/'policy.json','original-policy.json'),(other/'input.tar.gz.run.py','input.tar.gz.run.py'),(other/'generate_scene_presets.py','generate_scene_presets.py'),(partial/'results/candidate-1/study.json','original-study.json')]:shutil.copyfile(source,out/name)
spec={'bundle_sha256':expected['input-bundle.tar.gz'],'bootstrap_sha256':'b6cdfb6aa72d8336f0cbea8ee7dfe62a96ba2622cb3e6d7b23be72c3b5b721d6','cli_sha256':'c4044bf47bf11e2a0e460f4f697bafa0f87eae9e59a2cbcac0645be6e62f6cfd','policy_sha256':expected['policy.json'],'original_study_sha256':'76279e80f3d7a4a1170baba9221c1d1922d729a172bf3e9305049acc3dc75d6f','remote_sha256':sha(Path(__file__).with_name('remote.py')),'candidate1_identity':identity,'total_seconds':750}
for f,key in [('input.tar.gz.run.py','bootstrap_sha256'),('generate_scene_presets.py','cli_sha256'),('original-study.json','original_study_sha256')]:
 if sha(out/f)!=spec[key]:raise ValueError('Recovered helper checksum mismatch')
(out/'spec.json').write_text(json.dumps(spec,indent=2)+'\n')
print('Verified 100 + 69 accepted scenes; staged missing 069–099 and held-out 000–019.')
