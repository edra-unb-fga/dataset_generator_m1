"""Verify the exact complete natural-mixture study and accepted result bytes."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify(path, expected):
    path = Path(path)
    study = json.loads((path / 'study.json').read_text())
    jobs = study['jobs']
    if len(jobs) != expected or digest(study['contract']) != study['identity'] or digest(jobs) != study['contract']['jobs_sha256']:
        raise ValueError('Incomplete or unsealed study')
    if len({job['id'] for job in jobs}) != expected:
        raise ValueError('Duplicate jobs')
    for job in jobs:
        job_id = job['id']
        if Path(job_id).name != job_id or job_id in ('.', '..'):
            raise ValueError('Unsafe job identifier')
        scene = path / 'scenes' / job_id
        result = json.loads((scene / 'result.json').read_text())
        if result.get('status') != 'accepted' or result.get('identity') != study['identity'] or result.get('job') != job:
            raise ValueError('Invalid result identity or status')
        for name in ('rgb.png', 'masks.npz'):
            declared = result.get('files', {}).get(name)
            if isinstance(declared, dict):
                declared = declared.get('sha256')
            if not declared or hashlib.sha256((scene / name).read_bytes()).hexdigest() != declared:
                raise ValueError('Result checksum mismatch: ' + name)
        with np.load(scene / 'masks.npz', allow_pickle=False) as masks:
            if not {'visible', 'full'}.issubset(masks.files):
                raise ValueError('Missing masks')
    return study['identity']


if __name__ == '__main__':
    print(json.dumps({'status': 'complete', 'identity': verify(sys.argv[1], int(sys.argv[2]))}))
