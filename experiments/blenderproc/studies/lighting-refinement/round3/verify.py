"""Reject incomplete, unmatched or incorrectly transformed lighting triplets."""
import copy
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from transform import digest, transformed

root = Path(sys.argv[1]); expected = int(sys.argv[2]); groups = []
for kind in ('open', 'outdoor-night', 'indoor'):
    labels = [kind + '-' + v for v in ('baseline', 'broad', 'soft')]
    studies = [json.loads((root / label / 'study.json').read_text()) for label in labels]
    for study in studies:
        if len(study['jobs']) != expected or digest(study['contract']) != study['identity'] or digest(study['jobs']) != study['contract']['jobs_sha256']:
            raise ValueError('Incomplete or unsealed study')
    evidence = []
    for index, jobs in enumerate(zip(*(s['jobs'] for s in studies), strict=True)):
        base = jobs[0]
        # Compare all job fields, except paths to separately produced wear maps and intended lamps.
        def controls(job):
            job = copy.deepcopy(job)
            job['treatment'].pop('lamps')
            for manifest in job.get('wear_maps', []):
                for entry in manifest['maps'].values(): entry.pop('path', None)
            return job
        if any(controls(j) != controls(base) for j in jobs[1:]):
            raise ValueError(f'{kind} {index}: non-lighting job controls differ')
        for variant, job in zip(('baseline', 'broad', 'soft'), jobs, strict=True):
            if job['treatment']['lamps'] != transformed(base['treatment']['lamps'], variant):
                raise ValueError(f'{kind} {index}: incorrect {variant} lamps')
        hashes = []
        for label, job in zip(labels, jobs, strict=True):
            path = root / label / 'scenes' / job['id']
            result = json.loads((path / 'result.json').read_text())
            if result['status'] != 'accepted': raise ValueError(f'{label} {job["id"]}: not accepted')
            with np.load(path / 'masks.npz', allow_pickle=False) as masks:
                if not {'visible', 'full'}.issubset(masks.files): raise ValueError('Missing required masks')
                hashes.append({k: (str(masks[k].dtype), list(masks[k].shape), hashlib.sha256(masks[k].tobytes()).hexdigest()) for k in sorted(masks.files)})
        if len({json.dumps(x, sort_keys=True) for x in hashes}) != 1: raise ValueError('Mask mismatch')
        evidence.append({'job': base['id'], 'mask_hashes': hashes[0], 'baseline_lamps': base['treatment']['lamps'],
                         'broad_lamps': jobs[1]['treatment']['lamps'], 'soft_lamps': jobs[2]['treatment']['lamps'],
                         'preselected_review_case': index < 2})
    groups.append({'condition': kind, 'triplets': evidence})
(root / 'triplet-evidence.json').write_text(json.dumps({'status': 'complete', 'groups': groups}, indent=2) + '\n')
