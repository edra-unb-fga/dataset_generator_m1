"""Freeze project sources, real 2D assets, config, and study policy into a sealed bundle."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ['pyproject.toml', 'uv.lock', 'src/dataset_generator_m1', 'backgrounds',
           'foregrounds/landing_pad_foregrounds', 'examples/configs', 'examples/profiles',
           'scripts/study_effect_combinations.py', 'scripts/study_surface_2d.py',
           'scripts/guarded_effect_combinations.py', 'scripts/guarded_foreground_context.py', 'scripts/study_foreground_context.py', 'experiments/foreground-context/effect-combinations.json',
           'experiments/effect-combinations/colab-cpu-policy.json',
           'experiments/effect-combinations/colab-supervisor-policy.json']


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def build(output):
    output = Path(output).resolve()
    if output.exists(): raise FileExistsError(output)
    files=[]
    for entry in INCLUDE:
        path=ROOT/entry
        if not path.exists(): raise FileNotFoundError(path)
        files.extend([path] if path.is_file() else (p for p in path.rglob('*') if p.is_file()))
    files=sorted(p for p in files if '__pycache__' not in p.parts and not p.is_symlink())
    manifest={'schema_version':1,'files':{p.relative_to(ROOT).as_posix():sha(p) for p in files}}
    payload=json.dumps(manifest,sort_keys=True,separators=(',', ':')).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(output,'x:gz',compresslevel=3) as tar:
        for p in files: tar.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
        info=tarfile.TarInfo('bundle-manifest.json');info.size=len(payload);tar.addfile(info,io.BytesIO(payload))
    return {'bundle':str(output),'sha256':sha(output),'bytes':output.stat().st_size,'files':len(files)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    print(json.dumps(build(parser.parse_args().output),indent=2))
