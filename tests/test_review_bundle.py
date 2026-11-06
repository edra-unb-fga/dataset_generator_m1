import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from package_review_gallery import package, verify


def test_review_bundle_sanitizes_paths_and_verifies_inventory(tmp_path):
    gallery = tmp_path / 'gallery'
    (gallery / 'images').mkdir(parents=True)
    (gallery / 'profiles').mkdir()
    (gallery / 'images' / 'example.png').write_bytes(b'generated image')
    (gallery / 'profiles' / 'profile.json').write_text(json.dumps({'source': str(tmp_path / 'private' / 'image.jpg'),
        'source_hashes': {str(tmp_path / 'private' / 'image.jpg'): 'digest'}}))
    manifest = {'images': [{'path': 'images/example.png', 'family': 'landing', 'condition': 'test',
                            'metadata': {'profile_file': 'profiles/profile.json', 'workdir': str(tmp_path)}}]}
    (gallery / 'manifest.json').write_text(json.dumps(manifest))
    notes = tmp_path / 'notes.md'
    notes.write_text('Review [existing](index.html) and [absent](raw/secret.png).')
    archive = tmp_path / 'bundle.zip'
    result = package(gallery, archive, tmp_path, notes)
    assert result['verified'] and result['images'] == 1
    with zipfile.ZipFile(archive) as bundle:
        data = bundle.read('manifest.json').decode()
        profile = bundle.read('profiles/profile.json').decode()
        assert str(tmp_path) not in data + profile
        assert 'workspace/private/image.jpg' in profile
        assert json.loads(profile)['source_hashes'] == {'workspace/private/image.jpg': 'digest'}
        assert b'source not included in bundle' in bundle.read('notes.html')
        assert b'href="notes.html"' in bundle.read('index.html')
    assert verify(archive)['verified']


def test_review_bundle_rejects_escaping_image(tmp_path):
    gallery = tmp_path / 'gallery'
    gallery.mkdir()
    (tmp_path / 'secret.png').write_bytes(b'secret')
    (gallery / 'manifest.json').write_text(json.dumps({'images': [{'path': '../secret.png'}]}))
    with pytest.raises(ValueError, match='Unsafe'):
        package(gallery, tmp_path / 'bundle.zip', tmp_path)
    assert not (tmp_path / 'bundle.zip').exists()


def test_review_bundle_verifier_detects_tampering(tmp_path):
    gallery = tmp_path / 'gallery'
    gallery.mkdir()
    (gallery / 'sample.png').write_bytes(b'image')
    (gallery / 'manifest.json').write_text(json.dumps({'images': [{'path': 'sample.png'}]}))
    archive = tmp_path / 'valid.zip'
    package(gallery, archive, tmp_path)
    altered = tmp_path / 'altered.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(altered, 'w') as destination:
        for name in source.namelist():
            destination.writestr(name, b'tampered' if name == 'sample.png' else source.read(name))
    with pytest.raises(ValueError, match='Checksum mismatch'):
        verify(altered)
