import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_coherent_profile_review import collect_review


def test_fresh_3d_gallery_requires_verified_evidence_and_matching_images(tmp_path):
    capture = tmp_path / 'capture'
    capture.mkdir()
    (capture / 'capture-manifest.json').write_text(json.dumps({'images': []}))
    reviewed = tmp_path / 'reviewed'
    gallery = reviewed / 'gallery'
    gallery.mkdir(parents=True)
    image = gallery / 'sample.png'
    image.write_bytes(b'example image bytes')
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    (reviewed / 'evidence.json').write_text(json.dumps({'complete': True, 'provenance_verified': True}))
    (gallery / 'manifest.json').write_text(json.dumps({'images': [{
        'path': 'sample.png', 'engine': 'BlenderProc 3D', 'family': 'landing-pad',
        'condition': 'indoor', 'label': 'sample', 'metadata': {'image_sha256': digest},
    }]}))
    result = collect_review([], capture, tmp_path, tmp_path / 'out', reviewed)
    assert result['images'][0]['condition'] == 'fresh natural sample / indoor'
    assert (tmp_path / 'out' / result['images'][0]['path']).read_bytes() == image.read_bytes()
    image.write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        collect_review([], capture, tmp_path, tmp_path / 'invalid', reviewed)
