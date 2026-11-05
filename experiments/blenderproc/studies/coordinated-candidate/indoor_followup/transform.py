"""Reseal exact selected jobs after explicit, deterministic study-only treatments."""
import copy
import hashlib
import json
import sys
from pathlib import Path

VARIANTS = ('baseline', 'cap', 'fill', 'combined', 'no-casters')
SELECTED = ('003-base-fast', '008-base-fast', '018-base-fast')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def canonical_job(job):
    result = copy.deepcopy(job)
    for manifest in result.get('wear_maps', []):
        for entry in manifest['maps'].values(): entry.pop('path', None)
    reference = result.get('scene', {}).get('reference_image')
    if reference is not None: result['scene']['reference_image'] = Path(reference).name
    return result


def transform(job, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown variant')
    result = copy.deepcopy(job)
    lamps = result['treatment']['lamps']
    if variant in ('cap', 'combined'):
        total = sum(lamp['power_w'] for lamp in lamps)
        if total > 1200:
            for lamp in lamps:
                lamp['power_w'] *= 1200 / total
    if variant in ('fill', 'combined') and len(lamps) == 1 and lamps[0]['kind'] == 'SPOT':
        lamps.append({'kind': 'AREA', 'location': [0., 0., 3.], 'target': [0, 0, 0],
                      'color': [1., .95, .9], 'power_w': 150., 'size_m': 2.,
                      'spot_size_rad': .7853981633974483, 'spot_blend': .15})
    if variant == 'no-casters':
        result['casters'] = []
    return result


def main():
    path = Path(sys.argv[1]) / 'study.json'
    study = json.loads(path.read_text())
    if digest(study['contract']) != study['identity'] or digest(study['jobs']) != study['contract']['jobs_sha256']:
        raise ValueError('Unsealed study')
    by_id = {job['id']:job for job in study['jobs']}
    if any(name not in by_id for name in SELECTED): raise ValueError('Missing selected jobs')
    spec = json.loads(Path(sys.argv[3]).read_text())
    if any(digest(canonical_job(by_id[name])) != spec['original_job_hashes'].get(name) for name in SELECTED):
        raise ValueError('Prepared job differs from verified original')
    jobs = [transform(by_id[name], sys.argv[2]) for name in SELECTED]
    if any(job['environment_geometry'] != 'indoor' for job in jobs): raise ValueError('Expected indoor jobs')
    study['jobs'] = jobs
    study['contract']['jobs_sha256'] = digest(jobs)
    study['identity'] = digest(study['contract'])
    path.write_text(json.dumps(study, indent=2) + '\n')


if __name__ == '__main__': main()
