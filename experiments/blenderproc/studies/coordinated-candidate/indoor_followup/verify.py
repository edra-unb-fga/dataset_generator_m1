"""Verify matched selected cases, transformations and exact annotation masks."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from transform import digest, transform, SELECTED, VARIANTS


def verify(root):
    root = Path(root)
    studies = {variant:json.loads((root / variant / 'study.json').read_text()) for variant in VARIANTS}
    for variant, study in studies.items():
        if digest(study['contract']) != study['identity'] or digest(study['jobs']) != study['contract']['jobs_sha256']:
            raise ValueError('Unsealed ' + variant)
        if [job['id'] for job in study['jobs']] != list(SELECTED): raise ValueError('Wrong jobs')
    rows = []
    for index, job_id in enumerate(SELECTED):
        base = studies['baseline']['jobs'][index]
        signatures = []
        for variant, study in studies.items():
            job = study['jobs'][index]
            # Prepared wear maps differ only by workspace path; hashes and all other controls must match.
            def without_paths(job):
                job = copy.deepcopy(job)
                for manifest in job.get('wear_maps', []):
                    for entry in manifest['maps'].values(): entry.pop('path', None)
                return job
            if without_paths(job) != without_paths(transform(base, variant)): raise ValueError('Unmatched job '+variant)
            scene = root / variant / 'scenes' / job_id
            result = json.loads((scene / 'result.json').read_text())
            if result.get('status') != 'accepted' or result.get('identity') != study['identity'] or result.get('job') != job:
                raise ValueError('Bad result '+variant)
            for name in ('rgb.png', 'masks.npz'):
                expected = result.get('files', {}).get(name)
                if isinstance(expected, dict): expected = expected.get('sha256')
                if not expected or hashlib.sha256((scene / name).read_bytes()).hexdigest() != expected:
                    raise ValueError('Checksum mismatch '+name)
            with np.load(scene / 'masks.npz', allow_pickle=False) as masks:
                if not {'visible', 'full'}.issubset(masks.files): raise ValueError('Missing masks')
                signatures.append({k:(str(masks[k].dtype), masks[k].shape, hashlib.sha256(masks[k].tobytes()).hexdigest()) for k in sorted(masks.files)})
        if any(sig != signatures[0] for sig in signatures[1:4]): raise ValueError('Lighting variant masks differ '+job_id)
        rows.append({'job_id':job_id,'caster_diagnostic_masks_match':signatures[4] == signatures[0]})
    return {'status':'complete', 'jobs':len(SELECTED), 'variants':list(VARIANTS), 'diagnostics':rows}


if __name__ == '__main__': print(json.dumps(verify(sys.argv[1]), indent=2))
