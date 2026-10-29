"""Recover locally verified compact cell checkpoints from an extracted salvage folder."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=Path(a.input);out=Path(a.output)
if out.exists():raise ValueError('Refusing to overwrite an existing output')
out.mkdir(parents=True)
archives=sorted((root/'handoffs').glob('*.tar.gz'))
for archive in archives:
 with tarfile.open(archive) as tar:
  members=tar.getmembers();names=[m.name for m in members]
  if len(names)!=len(set(names)):raise ValueError('Duplicate archive members')
  manifest=json.load(tar.extractfile('compact-manifest.json'))
  for rec in manifest['files']:
   name=rec['path'];path=PurePosixPath(name)
   if path.is_absolute() or any(part in ('..','.') for part in path.parts):raise ValueError('Unsafe path')
   member=tar.getmember(name)
   if not member.isfile() or member.size!=rec['size']:raise ValueError('Invalid member')
   data=tar.extractfile(member).read()
   if hashlib.sha256(data).hexdigest()!=rec['sha256']:raise ValueError('Hash mismatch')
   target=out.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
if not (out/'matrix.json').exists():
 print('No completed compact handoffs were available.');raise SystemExit(0)
matrix=json.loads((out/'matrix.json').read_text());records=[]
for cell in matrix['cells']:
 path=out/'cells'/cell['id']/'summary.json'
 if path.is_file():records.append(json.loads(path.read_text()))
(out/'summary.json').write_text(json.dumps({'status':'recovered-partial','records':records,'recovered_cells':len(records)},indent=2)+'\n')
print('Recovered',len(records),'cells from',len(archives),'verified checkpoints')
