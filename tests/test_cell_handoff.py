import io
import json
from pathlib import Path
import tarfile

import pytest

from dataset_generator_m1.cell_handoff import package, import_archive, import_colab, inspect
from dataset_generator_m1.ownership import CoordinatorLease


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def study(tmp_path):
    root = tmp_path/'study'; cell = root/'cells'/'core'
    entry = {'name': 'core', 'status': 'settled', 'outcome': 'complete', 'evidence_identity': 'identity-a', 'charged_seconds': 3.0}
    _write(root/'budget.json', {'policy': {}, 'entries': [entry]})
    _write(root/'design.json', {'matrix_sha256': 'abcdef'})
    _write(root/'configs'/'core.json', {'seed': 1})
    _write(cell/'study.json', {'identity': 'identity-a'})
    _write(cell/'surface-origin.json', {'cell_id': 'core', 'matrix_sha256': 'abcdef'})
    _write(cell/'progress.json', {'status': 'complete'})
    _write(cell/'runs.json', [{'status': 'complete', 'command_seconds': 3.0}])
    _write(cell/'summary.json', {'n': 1})
    (cell/'scenes').mkdir(); (cell/'scenes'/'rgb.png').write_bytes(b'rgb')
    (cell/'scenes'/'mask.png').write_bytes(b'mask')
    (cell/'run.log').write_text('resource timing')
    return root


def test_package_import_resume_and_study_budget_growth(study, tmp_path):
    archive = tmp_path/'result.tar.gz'; out = tmp_path/'imports'
    first = package(study, 'core', archive)
    assert {x['path'] for x in first['files']} >= {'cell/scenes/rgb.png', 'cell/scenes/mask.png', 'cell/run.log', 'study/budget.json'}
    assert import_archive(archive, out)['status'] == 'imported'
    assert import_archive(archive, out)['status'] == 'already-imported'
    budget = json.loads((study/'budget.json').read_text()); budget['entries'].append({'name': 'later'})
    _write(study/'budget.json', budget)
    assert package(study, 'core', archive) == first
    (study/'cells'/'core'/'run.log').write_text('changed')
    with pytest.raises(ValueError, match='conflicts'):
        package(study, 'core', archive)
    (out/'core'/'cell'/'run.log').write_text('corrupt')
    with pytest.raises(ValueError, match='corrupt'):
        import_archive(archive, out)


def test_refuses_unsettled_missing_and_active(study, tmp_path):
    a = tmp_path/'a.tar.gz'
    with CoordinatorLease(study):
        with pytest.raises(RuntimeError, match='active coordinator'):
            package(study, 'core', a)
    p = study/'cells'/'core'/'progress.json'; _write(p, {'status': 'running'})
    with pytest.raises(ValueError, match='not complete'):
        package(study, 'core', a)
    _write(p, {'status': 'complete'}); (study/'cells'/'core'/'summary.json').unlink()
    with pytest.raises(ValueError, match='Incomplete'):
        package(study, 'core', a)
    assert not a.exists()


def test_rejects_symlinks(study, tmp_path):
    (study/'cells'/'core'/'link').symlink_to(study/'budget.json')
    with pytest.raises(ValueError, match='Symlinks'):
        package(study, 'core', tmp_path/'a.tar.gz')


def test_rejects_corrupted_and_unexpected_members(study, tmp_path):
    archive = tmp_path/'good.tar.gz'; package(study, 'core', archive)
    with tarfile.open(archive, 'r:gz') as src:
        members = [(m.name, src.extractfile(m).read()) for m in src.getmembers()]
    for mode in ('traversal', 'duplicate', 'corrupt', 'truncated'):
        bad = tmp_path/(mode+'.tar.gz')
        if mode == 'truncated':
            bad.write_bytes(archive.read_bytes()[:30])
        else:
            altered = list(members)
            if mode == 'traversal':
                manifest = json.loads(altered[0][1]); manifest['files'][0]['path'] = '../escape'
                altered[0] = ('manifest.json', json.dumps(manifest).encode())
                altered[1] = ('../escape', altered[1][1])
            if mode == 'duplicate': altered.append(altered[1])
            if mode == 'corrupt': altered[1] = (altered[1][0], b'x' * len(altered[1][1]))
            with tarfile.open(bad, 'w:gz') as out:
                for name, data in altered:
                    info = tarfile.TarInfo(name); info.size = len(data); out.addfile(info, io.BytesIO(data))
        with pytest.raises((ValueError, EOFError, OSError, tarfile.TarError)):
            import_archive(bad, tmp_path/'dest')
        assert not (tmp_path/'dest'/'core').exists()


def test_colab_fake_cli_fail_retry_and_cache(study, tmp_path, monkeypatch):
    import shutil
    from dataset_generator_m1 import cell_handoff
    archive = tmp_path/'remote.tar.gz'; package(study, 'core', archive)
    cli = tmp_path/'fake-cli'
    def fake_download(command, check):
        assert command[1:4] == ["download", "--session", "my-session"]
        shutil.copyfile(command[4], command[5])
    monkeypatch.setattr(cell_handoff.subprocess, 'run', fake_download)
    with pytest.raises(Exception):
        import_colab(str(tmp_path/'missing'), tmp_path/'dest', executable=cli, session='my-session', cache=tmp_path/'cache')
    assert not list((tmp_path/'cache').iterdir())
    assert import_colab(str(archive), tmp_path/'dest', executable=cli, session='my-session', cache=tmp_path/'cache')['status'] == 'imported'
    archive.unlink()
    assert import_colab(str(archive), tmp_path/'dest', executable=cli, session='my-session', cache=tmp_path/'cache')['status'] == 'already-imported'


def test_multiple_same_id_never_overwrite(study, tmp_path):
    archive = tmp_path/'one.tar.gz'; package(study, 'core', archive); import_archive(archive, tmp_path/'dest')
    (study/'cells'/'core'/'scenes'/'rgb.png').write_bytes(b'other')
    another = tmp_path/'two.tar.gz'; package(study, 'core', another)
    with pytest.raises(ValueError, match='conflicts'):
        import_archive(another, tmp_path/'dest')
    assert (tmp_path/'dest'/'core'/'cell'/'scenes'/'rgb.png').read_bytes() == b'rgb'


def test_held_study_lease_guards_entire_package_barrier(study, tmp_path):
    archive = tmp_path/'guarded.tar.gz'
    with CoordinatorLease(study) as lease:
        package(study, 'core', archive, lease=lease)
        with pytest.raises(RuntimeError, match='active coordinator'):
            with CoordinatorLease(study):
                pass
    with pytest.raises(ValueError, match='active lease'):
        package(study, 'core', tmp_path/'later.tar.gz', lease=lease)


def test_deadline_stops_packaging_and_keeps_study_lease(study, tmp_path):
    from time import monotonic
    from dataset_generator_m1.cell_handoff import package_with_deadline
    archive = tmp_path/'timeout.tar.gz'
    (study/'cells'/'core'/'extra.bin').write_bytes(b'x' * 1024 * 1024)
    with CoordinatorLease(study) as lease:
        with pytest.raises(TimeoutError, match='deadline'):
            package_with_deadline(study, 'core', archive, lease=lease, deadline=monotonic()+.001)
        assert not archive.exists()
        assert not list(tmp_path.glob('.cell-package-*'))
        with pytest.raises(RuntimeError, match='active coordinator'):
            with CoordinatorLease(study):pass
    assert (study/'cells'/'core'/'extra.bin').is_file()


def test_deadline_package_child_verifies_and_publishes(study, tmp_path):
    from time import monotonic
    from dataset_generator_m1.cell_handoff import package_with_deadline
    archive = tmp_path/'done.tar.gz'
    with CoordinatorLease(study) as lease:
        assert package_with_deadline(study, 'core', archive, lease=lease, deadline=monotonic()+15)['status']=='complete'
        assert package_with_deadline(study, 'core', archive, lease=lease, deadline=monotonic()+15)['status']=='already-packaged'
    assert import_archive(archive, tmp_path/'imports')['status']=='imported'
