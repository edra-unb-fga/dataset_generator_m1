"""Explicit portable Blender study inputs and a standalone Colab/local bootstrap.

The module's extraction/bootstrap path uses only Python's standard library. Run a copied
version directly with ARCHIVE --workspace DIRECTORY; BlenderProc manages Blender itself.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
from time import monotonic


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def safe_relative(value):
    path=PurePosixPath(value)
    if not value or str(path)!=value or path.as_posix()=='.' or path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value:
        raise ValueError('Unsafe bundle member: '+value)
    return path


def build_bundle(config_path, destination):
    from .blender_pilot import load_config, reference_scenes
    from .asset_licenses import validate_asset_license
    from .inspection import _LocalLinks
    config=load_config(config_path);reference_scenes(config.reference_pool)
    source=Path(__file__).resolve().parents[2];destination=Path(destination).resolve()
    bootstrap=destination.with_name(destination.name+'.run.py')
    if destination.exists() or bootstrap.exists():raise ValueError('Bundle or bootstrap destination already exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        staging=Path(temp);files={}
        def add(path,name):
            safe_relative(name);path=Path(path)
            if not path.is_file() or path.is_symlink():raise ValueError('Bundle needs a regular file: '+str(path))
            sha=file_hash(path)
            if name in files:
                if files[name]['sha256']!=sha:raise ValueError('Conflicting bundle files: '+name)
                return
            target=staging/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            files[name]={'sha256':sha,'bytes':target.stat().st_size}
        def write(name,value):
            target=staging/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(value,indent=2)+'\n')
            files[name]={'sha256':file_hash(target),'bytes':target.stat().st_size}
        # Explicit source roots only. No git metadata, credentials, arbitrary workspace or caches.
        for name in ['pyproject.toml','uv.lock','scripts/blenderproc_pilot.py','scripts/blenderproc_adaptive_guards.py','scripts/study_surface_integration.py','scripts/study_surface_performance.py','scripts/study_surface_2d.py','scripts/handoff_study_cell.py','scripts/study_camera_environments.py','scripts/select_blender_screen_profile.py']:
            add(source/name,'source/'+name)
        for base in [source/'src/dataset_generator_m1',source/'experiments/blenderproc']:
            for path in sorted(base.rglob('*')):
                if path.is_file() and path.suffix in {'.py','.json','.yaml','.md','.txt'} and '__pycache__' not in path.parts:
                    add(path,'source/'+path.relative_to(source).as_posix())
        value=config.model_dump(mode='json');value['reference_pool']='inputs/reference'
        value['artwork']=[]
        for index,path in enumerate(config.artwork):
            name=f'inputs/artwork-{index}'+path.suffix.lower();add(path,name);value['artwork'].append(name)
        value['grounds']=[]
        for index,g in enumerate(config.grounds):
            record=json.loads(g.material_file.read_text());validate_asset_license(record,redistribution=True)
            name=f'inputs/ground-{index}.json';write(name,record)
            for role,item in record['maps'].items():
                path=g.material_file.parent/record['asset_id']/(role+'.jpg')
                if file_hash(path)!=item['sha256']:raise ValueError('Ground map changed')
                add(path,'inputs/'+record['asset_id']+'/'+role+'.jpg')
            value['grounds'].append({'material_file':name})
        value['environments']=[]
        for index,path in enumerate(config.environments):
            record=json.loads(path.read_text());validate_asset_license(record,redistribution=True)
            hdr=path.parent/record['path']
            if file_hash(hdr)!=record['sha256']:raise ValueError('Environment changed')
            record['path']=f'environment-{index}.hdr';name=f'inputs/environment-{index}.json'
            add(hdr,'inputs/'+record['path']);write(name,record);value['environments'].append(name)
        if config.execution_policy:
            add(config.execution_policy,'inputs/execution-policy.json');value['execution_policy']='inputs/execution-policy.json'
        required={'run.json','summary.json','samples.jsonl','rejections.jsonl','metrics.jsonl','control.json','control-events.jsonl','qa/index.html'}
        for row in map(json.loads,filter(None,(config.reference_pool/'samples.jsonl').read_text().splitlines())):
            required.add(row['image_path'])
            if row.get('mask_evidence'):required.add(row['mask_evidence']['path'])
        parser=_LocalLinks();parser.feed((config.reference_pool/'qa/index.html').read_text())
        for link in parser.values:
            path=(config.reference_pool/'qa'/link).resolve()
            if not path.is_relative_to(config.reference_pool):raise ValueError('QA file escapes reference pool')
            required.add(path.relative_to(config.reference_pool).as_posix())
        for relative in sorted(required):
            path=(config.reference_pool/relative).resolve()
            if not path.is_relative_to(config.reference_pool):raise ValueError('Reference file escapes pool')
            add(path,'inputs/reference/'+path.relative_to(config.reference_pool).as_posix())
        write('config.json',value)
        if any(t.wear is not None for t in config.treatments):
            from .blender_pilot import prepare
            with tempfile.TemporaryDirectory() as prepared_temp:
                prepared=Path(prepared_temp)/'study'
                study=prepare(config_path,prepared)
                wear_hashes={}
                for job in study['jobs']:
                    if 'wear_maps' not in job:continue
                    wear_hashes[job['id']]=[]
                    for map_set in job['wear_maps']:
                        hashes={}
                        for role,entry in map_set['maps'].items():
                            path=Path(entry['path']);relative=path.relative_to(prepared)
                            add(path,'derivatives/'+relative.as_posix())
                            hashes[role]=entry['sha256']
                        wear_hashes[job['id']].append(hashes)
                write('derivatives/wear-hashes.json',wear_hashes)
        manifest={'schema_version':1,'files':files};manifest['identity']=identity(manifest)
        (staging/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        with tarfile.open(staging/'bundle.tar.gz','w:gz') as tar:
            for name in sorted([*files,'manifest.json']):tar.add(staging/name,arcname=name,recursive=False)
        shutil.move(staging/'bundle.tar.gz',destination)
    bootstrap=destination.with_name(destination.name+'.run.py')
    if bootstrap.exists():raise ValueError('Bootstrap destination already exists')
    shutil.copyfile(Path(__file__),bootstrap)
    return {'archive':str(destination),'sha256':file_hash(destination),'bytes':destination.stat().st_size,
            'identity':manifest['identity'],'files':len(files),'bootstrap':str(bootstrap),'bootstrap_sha256':file_hash(bootstrap)}


def unpack_bundle(archive, destination, *, expected_sha256=None, max_bytes=2*2**30):
    archive=Path(archive);destination=Path(destination)
    if destination.exists():raise ValueError('Workspace already exists; select a fresh directory')
    if expected_sha256 and file_hash(archive)!=expected_sha256:raise ValueError('Archive checksum mismatch')
    with tarfile.open(archive) as tar:
        members=tar.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)) or sum(m.size for m in members)>max_bytes:raise ValueError('Duplicate members or oversized bundle')
        for m in members:
            safe_relative(m.name)
            if not m.isfile():raise ValueError('Only regular bundle files are allowed')
        if 'manifest.json' not in names:raise ValueError('Missing bundle manifest')
        if next(m.size for m in members if m.name=='manifest.json')>8*1024**2:raise ValueError('Oversized bundle manifest')
        manifest=json.load(tar.extractfile('manifest.json'))
        if manifest.get('schema_version')!=1 or manifest.get('identity')!=identity({k:v for k,v in manifest.items() if k!='identity'}):raise ValueError('Invalid bundle manifest')
        if set(names)!={*manifest['files'],'manifest.json'}:raise ValueError('Bundle file set differs from manifest')
        # Verify every member before publishing any workspace, including archives on Python3.11.
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
            staging=Path(temp)/'workspace';staging.mkdir()
            for m in members:
                target=staging/m.name;target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(m) as src,target.open('wb') as out:shutil.copyfileobj(src,out)
                if m.name!='manifest.json':
                    expected=manifest['files'][m.name]
                    if target.stat().st_size!=expected['bytes'] or file_hash(target)!=expected['sha256']:raise ValueError('Bundle member checksum mismatch: '+m.name)
            staging.rename(destination)
    return manifest


def run_bundle(archive, workspace, *, expected_sha256=None, jobs=None, blender_install_path=None):
    workspace=Path(workspace).resolve();manifest=unpack_bundle(archive,workspace,expected_sha256=expected_sha256)
    started=monotonic();stages=[];current='startup'
    def record(status, **extra):
        value={'status':status,'bundle_identity':manifest['identity'],'seconds':monotonic()-started,'stages':stages,**extra}
        temporary=workspace/'bootstrap.tmp';temporary.write_text(json.dumps(value,indent=2));temporary.replace(workspace/'bootstrap.json')
    def run(name, command):
        nonlocal current
        current=name;stamp=monotonic()
        try:subprocess.run(command,check=True)
        finally:
            stages.append({'stage':name,'seconds':monotonic()-stamp});record('running',stage=name)
    try:
        record('running',stage=current)
        uv=shutil.which('uv')
        if not uv:raise RuntimeError('Install uv to bootstrap the pinned host and BlenderProc environments')
        source=workspace/'source';wrapper=workspace/'blenderproc-venv';study=workspace/'study'
        run('host-environment',[uv,'sync','--project',str(source),'--locked'])
        run('wrapper-environment',[uv,'venv','--python',sys.executable,str(wrapper)])
        python=wrapper/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
        blenderproc=wrapper/('Scripts/blenderproc.exe' if sys.platform=='win32' else 'bin/blenderproc')
        run('wrapper-dependencies',[uv,'pip','install','--python',str(python),'-r',str(source/'experiments/blenderproc/requirements.txt')])
        base=[uv,'run','--project',str(source),'--locked','python',str(source/'scripts/blenderproc_pilot.py')]
        config=json.loads((workspace/'config.json').read_text());config['input_bundle_identity']=manifest['identity']
        (workspace/'run-config.json').write_text(json.dumps(config,indent=2))
        run('prepare',[*base,'prepare','--config',str(workspace/'run-config.json'),'--output-dir',str(study)])
        expected_path=workspace/'derivatives/wear-hashes.json'
        if expected_path.exists():
            expected=json.loads(expected_path.read_text())
            prepared=json.loads((study/'study.json').read_text())
            actual={job['id']:[{role:entry['sha256'] for role,entry in item['maps'].items()} for item in job['wear_maps']]
                    for job in prepared['jobs'] if 'wear_maps' in job}
            if actual!=expected:raise ValueError('Bundle wear derivatives differ from prepared study')
        command=[*base,'render','--output-dir',str(study),'--blenderproc',str(blenderproc),'--blender-install-path',str(Path(blender_install_path).resolve() if blender_install_path else workspace/'blender')]
        if jobs:command.extend(['--jobs',*jobs])
        run('render',command)
        if json.loads((study/'progress.json').read_text())['status']!='complete':
            raise RuntimeError('Study stopped before completion; inspect its evidence before explicitly exporting partial output')
        run('export',[*base,'export','--output-dir',str(study)])
        run('report',[*base,'report','--output-dir',str(study)])
        (study/'bundle-origin.json').write_text(json.dumps({'bundle_identity':manifest['identity'],'archive_sha256':file_hash(archive)},indent=2))
        record('complete')
        return {'study':str(study),'bundle_identity':manifest['identity']}
    except BaseException as error:
        record('failed',stage=current,error=type(error).__name__)
        raise



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');p.add_argument('--workspace',required=True);p.add_argument('--expected-sha256');p.add_argument('--jobs',nargs='*');p.add_argument('--blender-install-path');a=p.parse_args()
    print(json.dumps(run_bundle(a.archive,a.workspace,expected_sha256=a.expected_sha256,jobs=a.jobs,blender_install_path=a.blender_install_path),indent=2))
