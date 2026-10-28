"""Transfer settled study cells at explicit between-render barriers.

Archives are immutable snapshots: a resumed download restarts that one archive, while
verified cells already imported remain available. No runtime credentials are stored.
"""
from __future__ import annotations

import hashlib
from contextlib import nullcontext
import io
import json
import multiprocessing
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
from time import monotonic

from .ownership import CoordinatorLease

SCHEMA = 1
_ID = re.compile(r'^[a-z0-9][a-z0-9-]*$')


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _safe(name: str) -> str:
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or '\x00' in name or p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise ValueError(f'Unsafe archive path: {name!r}')
    return name


def _file_record(path: Path, name: str) -> dict:
    before = path.stat(follow_symlinks=False)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Non-regular evidence file: {path}')
    digest = _hash(path)
    after = path.stat(follow_symlinks=False)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError(f'Evidence changed while packaging: {path}')
    return {'path': _safe(name), 'size': before.st_size, 'sha256': digest}


def _inputs(root: Path, cell_id: str):
    if not _ID.fullmatch(cell_id):
        raise ValueError('Invalid cell ID')
    cell = root / 'cells' / cell_id
    required = [cell/'study.json', cell/'surface-origin.json', cell/'progress.json', cell/'runs.json',
                cell/'summary.json', root/'budget.json', root/'design.json', root/'configs'/f'{cell_id}.json']
    if not all(p.is_file() and not p.is_symlink() for p in required):
        raise ValueError('Incomplete cell or missing study evidence')
    study, origin, progress, runs, budget, design = map(_json, (required[0], required[1], required[2], required[3], required[5], required[6]))
    entries = [e for e in budget['entries'] if e['name'] == cell_id]
    if (len(entries) != 1 or entries[0]['status'] != 'settled' or entries[0].get('outcome') != 'complete'
            or progress.get('status') != 'complete' or not runs or runs[-1].get('status') != 'complete'
            or entries[0].get('evidence_identity') != study.get('identity') or origin.get('cell_id') != cell_id
            or origin.get('matrix_sha256') != design.get('matrix_sha256') or not origin.get('matrix_sha256')):
        raise ValueError('Cell is not complete and settled with matching identity')
    if not isinstance(study.get('identity'), str) or not study['identity']:
        raise ValueError('Missing study identity')
    files = []
    for path in sorted(cell.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlinks are not allowed: {path}')
        if path.is_file():
            files.append((path, 'cell/' + path.relative_to(cell).as_posix()))
        elif not path.is_dir():
            raise ValueError(f'Non-regular evidence file: {path}')
    files.extend((p, 'study/' + p.relative_to(root).as_posix()) for p in required[5:])
    records = [_file_record(path, name) for path, name in files]
    manifest = {'schema_version': SCHEMA, 'cell_id': cell_id, 'study_identity': study['identity'],
                'budget_entry': entries[0], 'files': records}
    return files, manifest


def _manifest_bytes(manifest):
    return (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _validate_lease(root, lease):
    if (not isinstance(lease, CoordinatorLease) or lease.root != root or
            lease.handle is None or lease.handle.closed):
        raise ValueError('An active lease for this study is required')


def _stage_package(root, cell_id, archive, temporary):
    """Build and verify temporary evidence; never publish it."""
    files, manifest = _inputs(root, cell_id)
    if archive.exists():
        old = inspect(archive)
        # Later completed cells may extend the study-wide budget snapshot.
        def stable(m):
            return (m['cell_id'], m['study_identity'], m['budget_entry'],
                    [r for r in m['files'] if r['path'] != 'study/budget.json'])
        if stable(old) != stable(manifest):
            raise ValueError('Existing archive conflicts with current cell')
        return old, False
    with tarfile.open(temporary, 'w:gz') as tar:
        data = _manifest_bytes(manifest)
        info = tarfile.TarInfo('manifest.json'); info.size = len(data); info.mtime = 0
        tar.addfile(info, io.BytesIO(data))
        for (path, name), rec in zip(files, manifest['files'], strict=True):
            info = tarfile.TarInfo(name); info.size = rec['size']; info.mtime = 0
            with path.open('rb') as source:
                tar.addfile(info, source)
    if inspect(temporary) != manifest:
        raise ValueError('Packaged evidence verification failed')
    _, final = _inputs(root, cell_id)
    if final != manifest:
        raise ValueError('Evidence changed while packaging')
    return manifest, True


def package(root, cell_id, archive, *, lease=None):
    """Freeze an archive under the study lease, optionally held by the caller."""
    root, archive = Path(root).resolve(), Path(archive).resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    if lease is not None:
        _validate_lease(root, lease)
    with (nullcontext(lease) if lease is not None else CoordinatorLease(root)):
        fd, temporary = tempfile.mkstemp(prefix='.cell-package-', dir=archive.parent)
        os.close(fd)
        try:
            manifest, publish = _stage_package(root, cell_id, archive, temporary)
            if publish:
                os.link(temporary, archive)  # create only; never replace another archive
        finally:
            Path(temporary).unlink(missing_ok=True)
    return manifest


def _deadline_package_child(root, cell_id, archive, temporary, send):
    try:
        _, publish = _stage_package(root, cell_id, archive, temporary)
        send.send(('complete', publish))
    except BaseException as exc:
        send.send(('failed', type(exc).__name__ + ': ' + str(exc)))
    finally:
        send.close()


def package_with_deadline(root, cell_id, archive, *, lease, deadline):
    """Package under a held lease, ending compression at an absolute monotonic deadline.

    The child only builds a private temporary archive. The lease-owning parent
    publishes it after successful completion, or kills and joins the child on
    timeout or interruption before deleting the temporary archive.
    """
    root, archive = Path(root).resolve(), Path(archive).resolve()
    _validate_lease(root, lease)
    if deadline <= monotonic():
        raise TimeoutError('Packaging deadline expired')
    archive.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.cell-package-', dir=archive.parent)
    os.close(fd)
    ctx = multiprocessing.get_context('spawn')
    recv, send = ctx.Pipe(duplex=False)
    child = ctx.Process(target=_deadline_package_child,
                        args=(root, cell_id, archive, temporary, send), daemon=True)
    started = False
    try:
        child.start(); started = True; send.close()
        if not recv.poll(max(0., deadline-monotonic())):
            raise TimeoutError('Packaging deadline expired')
        status, detail = recv.recv()
        child.join(max(0., deadline-monotonic()))
        if child.is_alive() or monotonic() >= deadline:
            raise TimeoutError('Packaging deadline expired')
        if status != 'complete' or child.exitcode != 0:
            raise ValueError('Packaging failed: ' + str(detail))
        if detail:
            os.link(temporary, archive)
        return {'status': 'complete' if detail else 'already-packaged'}
    finally:
        send.close(); recv.close()
        if started and child.is_alive():
            child.terminate(); child.join(2)
            if child.is_alive():
                child.kill(); child.join()
        if started:
            child.close()
        Path(temporary).unlink(missing_ok=True)


def inspect(archive):
    """Validate all archive paths, sizes and hashes without trusting tar extraction."""
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if not members or members[0].name != 'manifest.json' or not members[0].isfile():
            raise ValueError('Missing handoff manifest')
        if members[0].size > 10_000_000:
            raise ValueError('Handoff manifest is too large')
        manifest = json.load(tar.extractfile(members[0]))
        if manifest.get('schema_version') != SCHEMA or not _ID.fullmatch(manifest.get('cell_id', '')):
            raise ValueError('Invalid handoff manifest')
        records = manifest.get('files')
        if not isinstance(records, list) or len(records) != len(members)-1:
            raise ValueError('Missing or extra archive members')
        names = set()
        for rec, member in zip(records, members[1:], strict=True):
            name = _safe(rec['path'])
            if (name in names or name != member.name or not member.isfile() or
                    not (name.startswith('cell/') or name.startswith('study/')) or
                    not isinstance(rec['size'], int) or rec['size'] < 0 or rec['size'] != member.size):
                raise ValueError('Invalid or duplicate archive member')
            names.add(name)
            h = hashlib.sha256()
            with tar.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != rec['sha256']:
                raise ValueError(f'Evidence hash mismatch: {name}')
        needed = {'cell/study.json', 'cell/surface-origin.json', 'cell/progress.json', 'cell/runs.json',
                  'cell/summary.json', 'study/budget.json', 'study/design.json', f"study/configs/{manifest['cell_id']}.json"}
        if not needed.issubset(names):
            raise ValueError('Archive lacks required cell evidence')
        def read_json(name):
            member = tar.getmember(name)
            if member.size > 50_000_000:
                raise ValueError('Oversized JSON evidence')
            return json.load(tar.extractfile(member))
        study = read_json('cell/study.json')
        origin = read_json('cell/surface-origin.json')
        progress = read_json('cell/progress.json')
        runs = read_json('cell/runs.json')
        budget = read_json('study/budget.json')
        design = read_json('study/design.json')
        entries = [e for e in budget['entries'] if e.get('name') == manifest['cell_id']]
        if (len(entries) != 1 or entries[0] != manifest.get('budget_entry') or
                entries[0].get('status') != 'settled' or entries[0].get('outcome') != 'complete' or
                not manifest.get('study_identity') or study.get('identity') != manifest['study_identity'] or
                entries[0].get('evidence_identity') != manifest['study_identity'] or
                origin.get('cell_id') != manifest['cell_id'] or not origin.get('matrix_sha256') or
                origin['matrix_sha256'] != design.get('matrix_sha256') or progress.get('status') != 'complete' or
                not runs or runs[-1].get('status') != 'complete'):
            raise ValueError('Archive identity, completion or budget evidence disagrees')
    return manifest


def _verify_import(destination: Path, manifest):
    if not (destination/'manifest.json').is_file() or _json(destination/'manifest.json') != manifest:
        raise ValueError('Existing imported cell conflicts with archive')
    expected = {'manifest.json', *(r['path'] for r in manifest['files'])}
    actual = set()
    for path in destination.rglob('*'):
        if path.is_symlink():
            raise ValueError('Imported evidence contains a symlink')
        if path.is_file():
            actual.add(path.relative_to(destination).as_posix())
    if actual != expected:
        raise ValueError('Imported evidence has missing or extra files')
    for rec in manifest['files']:
        path = destination / rec['path']
        if path.stat().st_size != rec['size'] or _hash(path) != rec['sha256']:
            raise ValueError('Imported evidence is corrupt')


def import_archive(archive, output):
    """Verify and atomically promote one cell; a mismatch never overwrites it."""
    archive, output = Path(archive).resolve(), Path(output).resolve()
    manifest = inspect(archive)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / manifest['cell_id']
    with CoordinatorLease(output):
        if destination.exists():
            _verify_import(destination, manifest)
            return {'status': 'already-imported', 'path': str(destination), 'identity': manifest['study_identity']}
        staging = Path(tempfile.mkdtemp(prefix='.cell-import-', dir=output))
        try:
            (staging/'manifest.json').write_bytes(_manifest_bytes(manifest))
            with tarfile.open(archive, 'r:gz') as tar:
                for rec in manifest['files']:
                    path = staging / rec['path']; path.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(rec['path']) as src, path.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
            _verify_import(staging, manifest)
            os.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return {'status': 'imported', 'path': str(destination), 'identity': manifest['study_identity']}


def import_colab(remote, output, *, executable, session, cache):
    """Download using an explicit CLI executable/session, then verify before import.

    Call only at a between-cell barrier. On transfer failure, restart this archive's
    download; successfully imported cells and their archives remain untouched.
    """
    cache = Path(cache).resolve(); cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((session + '\0' + remote).encode()).hexdigest()
    archive = cache / (key + '.tar.gz')
    if not archive.exists():
        fd, name = tempfile.mkstemp(prefix='.download-', dir=cache); os.close(fd)
        try:
            subprocess.run([str(executable), 'download', '--session', session, remote, name], check=True)
            inspect(name)
            os.link(name, archive)
        finally:
            Path(name).unlink(missing_ok=True)
    return import_archive(archive, output)
