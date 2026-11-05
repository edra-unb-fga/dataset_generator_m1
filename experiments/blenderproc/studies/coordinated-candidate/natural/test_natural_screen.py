import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('natural_verifier', HERE / 'verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_verifier_rejects_corruption_and_incomplete_data(tmp_path):
    job = {'id': 'a', 'seed': 1}
    contract = {'jobs_sha256': module.digest([job])}
    identity = module.digest(contract)
    (tmp_path / 'study.json').write_text(json.dumps({'jobs': [job], 'identity': identity, 'contract': contract}))
    scene = tmp_path / 'scenes' / 'a'
    scene.mkdir(parents=True)
    (scene / 'rgb.png').write_bytes(b'image')
    np.savez(scene / 'masks.npz', visible=np.array([1]), full=np.array([1]))
    hashes = {name: hashlib.sha256((scene / name).read_bytes()).hexdigest() for name in ('rgb.png', 'masks.npz')}
    (scene / 'result.json').write_text(json.dumps({'status': 'accepted', 'identity': identity, 'job': job, 'files': hashes}))
    assert module.verify(tmp_path, 1) == identity
    with pytest.raises(ValueError):
        module.verify(tmp_path, 2)
    (scene / 'rgb.png').write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='checksum'):
        module.verify(tmp_path, 1)
