import importlib.util
import html
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'scene_review_gallery', Path(__file__).parents[1] / 'scripts' / 'build_scene_review_gallery.py'
)
gallery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gallery)


def test_gallery_escapes_metadata_and_references_real_images(tmp_path):
    (tmp_path / 'target image.png').write_bytes(b'fake PNG for path validation')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'title': '<review>', 'images': [{
        'path': 'target image.png', 'engine': '2d', 'family': 'pad',
        'condition': 'sun', 'label': '<img>', 'metadata': {'seed': 42, 'note': '<script>'},
    }]}))
    report = tmp_path / 'index.html'
    assert gallery.build(manifest, report) == 1
    text = report.read_text()
    assert 'target%20image.png' in text
    assert '&lt;script&gt;' in text and '&lt;review&gt;' in text
    assert 'requestFullscreen' in text and 'showModal' in text
    assert 'large-metadata' in text
    assert 'data-family="pad"' in text and '"seed": 42' in html.unescape(text)


def test_gallery_rejects_missing_or_outside_images(tmp_path):
    manifest = tmp_path / 'manifest.json'
    for path in ('missing.png', '../outside.png'):
        manifest.write_text(json.dumps({'images': [{'path': path}]}))
        with pytest.raises(ValueError, match='must exist inside'):
            gallery.build(manifest, tmp_path / 'index.html')


def test_gallery_never_overwrites_manifest(tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{"images": []}')
    with pytest.raises(ValueError, match='must not overwrite'):
        gallery.build(manifest, manifest)
    assert json.loads(manifest.read_text()) == {'images': []}
