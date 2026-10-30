import importlib.util,json,tarfile,time,hashlib
from pathlib import Path
spec=importlib.util.spec_from_file_location('compact_driver',str(Path(__file__).resolve().parents[1]/'experiments/blenderproc/studies/effect-combinations-retry/compact-driver.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
def test_compact_checkpoint(tmp_path):
 root=tmp_path/'results';cell=root/'cells'/'wear';scene=cell/'scenes'/'000-core-fast';scene.mkdir(parents=True);(cell/'wear').mkdir()
 for name in ('matrix.json','design.json','provenance.json','budget.json'):(root/name).write_text('{}')
 for name in ('study.json','surface-origin.json','progress.json','runs.json','summary.json','execution.json'):(cell/name).write_text('{}')
 for name in ('result.json','rgb.png','masks.npz'):(scene/name).write_bytes(b'evidence')
 (cell/'wear'/'map.png').write_bytes(b'duplicated-map')
 archive=tmp_path/'handoffs'/'wear.tar.gz';mod.compact_handoff(root,'wear',archive,object(),time.monotonic()+60)
 with tarfile.open(archive) as tar:
  names=tar.getnames();assert not any('/wear/wear/' in x for x in names);assert 'cells/wear/scenes/000-core-fast/rgb.png' in names
  manifest=json.load(tar.extractfile('compact-manifest.json'))
  for record in manifest['files']:
   data=tar.extractfile(record['path']).read();assert len(data)==record['size'];assert hashlib.sha256(data).hexdigest()==record['sha256']

def test_matrix_size():
 matrix=json.load(open(Path(__file__).resolve().parents[1]/'experiments/blenderproc/studies/effect-combinations-retry/development-matrix.json'))
 assert len(matrix['cells'])==5
 assert all(c['config']['scenes']==3 and len(c['jobs'])==4 for c in matrix['cells'])
