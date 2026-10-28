"""Portable extraction is atomic, bounded and integrity checked without Blender."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from dataset_generator_m1.blender_bundle import file_hash, identity, safe_relative, unpack_bundle


def archive(tmp_path, *, changed=False, extra=False, link=False):
    path=tmp_path/'input.tar.gz';data=b'example'
    manifest={'schema_version':1,'files':{'source/a.txt':{'bytes':len(data),'sha256':__import__('hashlib').sha256(data).hexdigest()}}}
    manifest['identity']=identity(manifest)
    with tarfile.open(path,'w:gz') as tar:
        for name,value in [('manifest.json',json.dumps(manifest).encode()),('source/a.txt',b'changed' if changed else data)]:
            member=tarfile.TarInfo(name);member.size=len(value);tar.addfile(member,io.BytesIO(value))
        if extra:
            member=tarfile.TarInfo('extra.txt');member.size=1;tar.addfile(member,io.BytesIO(b'x'))
        if link:
            member=tarfile.TarInfo('link');member.type=tarfile.SYMTYPE;member.linkname='/tmp/outside';tar.addfile(member)
    return path


def test_verified_extraction_and_refusal_to_overwrite(tmp_path):
    path=archive(tmp_path);target=tmp_path/'workspace';value=unpack_bundle(path,target,expected_sha256=file_hash(path))
    assert (target/'source/a.txt').read_bytes()==b'example' and value['schema_version']==1
    with pytest.raises(ValueError,match='exists'):unpack_bundle(path,target)


@pytest.mark.parametrize('option',[{'changed':True},{'extra':True},{'link':True}])
def test_corruption_or_unlisted_files_never_publish_workspace(tmp_path,option):
    path=archive(tmp_path,**option);target=tmp_path/'workspace'
    with pytest.raises(ValueError):unpack_bundle(path,target)
    assert not target.exists()


def test_size_and_archive_hash_are_checked_before_extraction(tmp_path):
    path=archive(tmp_path)
    with pytest.raises(ValueError,match='checksum'):unpack_bundle(path,tmp_path/'bad-hash',expected_sha256='0'*64)
    with pytest.raises(ValueError,match='oversized'):unpack_bundle(path,tmp_path/'too-large',max_bytes=1)


@pytest.mark.parametrize('value',['../a','/tmp/a','a/../b','a\\b','C:/x','./a','a//b','.',''])
def test_noncanonical_and_escaping_member_names_rejected(value):
    with pytest.raises(ValueError):safe_relative(value)


def test_standalone_bootstrap_help_needs_no_project_installation():
    script=Path('src/dataset_generator_m1/blender_bundle.py').resolve()
    result=subprocess.run([sys.executable,'-I',str(script),'--help'],capture_output=True,text=True)
    assert result.returncode==0 and '--workspace' in result.stdout


def test_bootstrap_preserves_budget_limited_outputs_without_export(tmp_path,monkeypatch):
    from dataset_generator_m1 import blender_bundle as bundle
    workspace=tmp_path/'work';calls=[]
    def unpack(*args,**kwargs):
        workspace.mkdir();(workspace/'config.json').write_text('{}');return {'identity':'a'*64}
    def run(command,**kwargs):
        calls.append(command)
        if 'render' in command:
            (workspace/'study').mkdir();(workspace/'study/progress.json').write_text('{"status":"budget-limited"}')
    monkeypatch.setattr(bundle,'unpack_bundle',unpack);monkeypatch.setattr(bundle.shutil,'which',lambda value:'uv')
    monkeypatch.setattr(bundle.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='before completion'):bundle.run_bundle(tmp_path/'archive',workspace)
    assert not any('export' in call for call in calls)
