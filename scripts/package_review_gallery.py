#!/usr/bin/env python3
"""Package a manifest-based review gallery without raw input assets.

Only referenced generated images and profile snapshots are included. Paths in
metadata are sanitized; this is an inspection bundle, not a replacement for the
raw pools or source assets needed to reproduce a study.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

from build_scene_review_gallery import build
from review_markdown import render_review_markdown


def _safe_path(root: Path, relative: str) -> Path:
    part = PurePosixPath(relative)
    if not relative or part.is_absolute() or '..' in part.parts or '\\' in relative:
        raise ValueError(f'Unsafe relative path: {relative!r}')
    resolved = (root / Path(*part.parts)).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f'Missing or escaping gallery file: {relative}')
    return resolved


def _sanitize(value, workspace: Path):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            safe_key = _sanitize(key, workspace) if isinstance(key, str) else key
            if safe_key in result:
                raise ValueError('Path sanitization produced duplicate metadata keys')
            result[safe_key] = _sanitize(item, workspace)
        return result
    if isinstance(value, list):
        return [_sanitize(v, workspace) for v in value]
    if not isinstance(value, str):
        return value
    value = value.replace(str(workspace), 'workspace')
    # Strip remaining absolute filesystem paths, including paths embedded in a
    # command. Keep URL slashes intact and distinguish external paths with the
    # same basename so source-hash mapping keys do not silently collide.
    def external(match):
        source = match.group(0)
        fingerprint = hashlib.sha256(source.encode()).hexdigest()[:12]
        return f'external/{Path(source).name}-{fingerprint}'
    return re.sub(r'(?<![A-Za-z0-9:/.])/(?!/)[^\s"<>]+', external, value)


def _portable_note_links(text: str, root: Path) -> str:
    def rewrite(match):
        label, reference = match.group(1), match.group(2)
        if reference.startswith(('https://', 'http://', '#', 'mailto:')):
            return match.group(0)
        path = reference.split('#', 1)[0]
        try:
            _safe_path(root, path)
            return match.group(0)
        except ValueError:
            return f'{label} (source not included in bundle)'
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', rewrite, text)


def package(gallery: Path, archive: Path, workspace: Path, notes: Path | None = None) -> dict:
    gallery, archive, workspace = gallery.resolve(), archive.resolve(), workspace.resolve()
    if archive.exists() or archive.is_relative_to(gallery):
        raise ValueError('Use a fresh archive outside the source gallery')
    manifest = json.loads((gallery / 'manifest.json').read_text())
    if not isinstance(manifest.get('images'), list) or not manifest['images']:
        raise ValueError('Gallery must have a nonempty images list')
    with tempfile.TemporaryDirectory(prefix='review-package-') as temporary:
        stage = Path(temporary).resolve()
        for row in manifest['images']:
            image = row['path']
            source = _safe_path(gallery, image)
            destination = stage / image
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            profile = row.get('metadata', {}).get('profile_file')
            if profile:
                source_profile = _safe_path(gallery, profile)
                destination_profile = stage / profile
                destination_profile.parent.mkdir(parents=True, exist_ok=True)
                payload = json.loads(source_profile.read_text())
                destination_profile.write_text(json.dumps(_sanitize(payload, workspace), ensure_ascii=False, indent=2) + '\n')
        sanitized = _sanitize(manifest, workspace)
        (stage / 'manifest.json').write_text(json.dumps(sanitized, ensure_ascii=False, indent=2) + '\n')
        build(stage / 'manifest.json', stage / 'index.html')
        note_text = ('# Portable review bundle\n\nOpen [the gallery](index.html). Generated images and '
                     'sanitized profile snapshots are included. Source assets and raw pools are not included; '
                     'use recorded hashes and study definitions to locate them for reproduction. '
                     'Visual findings are not evidence of detector performance.\n')
        if notes is not None:
            note_text += '\n' + _portable_note_links(_sanitize(notes.read_text(), workspace), stage)
        (stage / 'notes.md').write_text(note_text)
        (stage / 'notes.html').write_bytes(render_review_markdown(note_text, 'Review notes'))
        page = (stage / 'index.html').read_text()
        anchor = '<div id="filters"></div>'
        if page.count(anchor) != 1:
            raise ValueError('Unexpected gallery template')
        (stage / 'index.html').write_text(page.replace(anchor, '<p><a href="notes.html">Review notes and dependencies</a></p>' + anchor))
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        checksums = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        (stage / 'checksums.json').write_text(json.dumps(checksums, indent=2, sort_keys=True) + '\n')
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=4) as bundle:
            for path in sorted(p for p in stage.rglob('*') if p.is_file()):
                bundle.write(path, path.relative_to(stage).as_posix())
    result = verify(archive)
    return result


def verify(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix='review-verify-') as temporary:
        root = Path(temporary).resolve()
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate archive entries')
            for name in names:
                part = PurePosixPath(name)
                if part.is_absolute() or '..' in part.parts or '\\' in name or name.endswith('/'):
                    raise ValueError(f'Unsafe archive entry: {name}')
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as source, target.open('wb') as destination:
                    shutil.copyfileobj(source, destination)
        expected = json.loads((root / 'checksums.json').read_text())
        if set(names) != set(expected) | {'checksums.json'}:
            raise ValueError('Archive inventory differs from checksums')
        for name, digest in expected.items():
            if hashlib.sha256(_safe_path(root, name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Checksum mismatch: {name}')
        manifest = json.loads((root / 'manifest.json').read_text())
        for row in manifest['images']:
            _safe_path(root, row['path'])
            profile = row.get('metadata', {}).get('profile_file')
            if profile:
                _safe_path(root, profile)
        for name in ('index.html', 'notes.html'):
            _safe_path(root, name)
        return {'images': len(manifest['images']), 'files': len(names),
                'sha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
                'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gallery', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--notes', type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.gallery, args.archive, args.workspace, args.notes), indent=2))


if __name__ == '__main__':
    main()
