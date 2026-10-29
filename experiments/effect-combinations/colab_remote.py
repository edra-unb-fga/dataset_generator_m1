"""Run a sealed 2D study in Colab and package partial evidence in all normal exits."""
import hashlib, importlib.util, json, os, signal, subprocess, tarfile, time, traceback
from pathlib import Path

content=Path('/content');spec=json.loads((content/'context-phase.json').read_text())
root=content/('context-'+spec['phase']);root.mkdir();started=time.monotonic();state='failed';error=None

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def run(command, seconds, log, cwd=None):
    with log.open('w') as out:
        p=subprocess.Popen(command,cwd=cwd,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=p.wait(timeout=seconds)
            if code:raise RuntimeError(f'Command exited {code}: {command[0]}')
        except BaseException:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            raise

try:
    archive=content/'context-input.tar.gz'
    helper=content/'context_chunking.py'
    if digest(helper)!=spec['chunk_helper_sha256']:raise ValueError('Chunk helper checksum mismatch')
    module_spec=importlib.util.spec_from_file_location('context_chunking',helper)
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    module.assemble_bundle(content,archive,spec['transfer'])
    if digest(archive)!=spec['bundle_sha256']:raise ValueError('Bundle checksum mismatch')
    source=root/'source';source.mkdir()
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            if not member.isfile() or Path(member.name).is_absolute() or '..' in Path(member.name).parts:
                raise ValueError('Unsafe bundle member')
        tar.extractall(source,filter='data')
    manifest=json.loads((source/'bundle-manifest.json').read_text())
    for name,expected in manifest['files'].items():
        if digest(source/name)!=expected:raise ValueError('Input file checksum mismatch: '+name)
    run(['uv','sync','--project',str(source),'--locked','--no-dev'],180,root/'setup.log')
    remaining=spec['remote_seconds']-(time.monotonic()-started)
    if remaining<60:raise TimeoutError('No time remains for generation')
    python=source/'.venv/bin/python'
    run([str(python),str(source/'scripts/guarded_effect_combinations.py'),
         '--config',str(source/'examples/configs/landing-pad_surface-pristine.yaml'), '--phase',spec['phase'],
         '--samples',str(spec['samples']),'--policy',str(source/'experiments/effect-combinations/colab-cpu-policy.json'),
         '--matrix',str(source/'experiments/foreground-context/effect-combinations.json'),
         '--output-dir',str(root/'results')],remaining-30,root/'study.log',cwd=source)
    state='complete'
except BaseException as exc:
    error=f'{type(exc).__name__}: {exc}';traceback.print_exc()
finally:
    try:
        archive=content/'context-results.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
            for path in [root/'results',*root.glob('*.log'),content/'context-phase.json']:
                if path.exists():tar.add(path,arcname=path.name)
        (content/'context-results.json').write_text(json.dumps({'status':state,'error':error,'sha256':digest(archive),
            'bytes':archive.stat().st_size,'wall_seconds':time.monotonic()-started},indent=2))
    except BaseException as exc:
        (content/'context-results.json').write_text(json.dumps({'status':'archive-failed','error':str(exc)}));raise
