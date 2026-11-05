"""Apply deterministic lighting-only treatments and reseal the prepared pilot contract."""
import copy
import hashlib
import json
import sys
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def transformed(lamps, variant):
    result = copy.deepcopy(lamps)
    if variant not in ('baseline', 'soft', 'soft-fill'):
        raise ValueError('Unknown variant')
    if variant != 'baseline':
        for lamp in result:
            # Reduce main lamp power moderately while broadening emitters and spots.
            lamp['power_w'] *= 0.8
            lamp['size_m'] = min(3.0, lamp['size_m'] * 2.0)
            lamp['spot_size_rad'] = min(2.4, lamp['spot_size_rad'] * 1.5)
            lamp['spot_blend'] = min(1.0, lamp['spot_blend'] + 0.3)
    if variant == 'soft-fill':
        result.append({'kind': 'AREA', 'location': [0.0, 0.0, 2.5], 'target': [0, 0, 0],
                       'color': [1.0, 0.95, 0.9], 'power_w': 60.0, 'size_m': 1.0,
                       'spot_size_rad': 0.7853981633974483, 'spot_blend': 0.15})
    return result


def main():
    path = Path(sys.argv[1]) / 'study.json'
    variant = sys.argv[2]
    study = json.loads(path.read_text())
    if digest(study['contract']) != study['identity'] or digest(study['jobs']) != study['contract']['jobs_sha256']:
        raise ValueError('Unsealed input study')
    for job in study['jobs']:
        job['treatment']['lamps'] = transformed(job['treatment']['lamps'], variant)
    study['contract']['jobs_sha256'] = digest(study['jobs'])
    study['identity'] = digest(study['contract'])
    path.write_text(json.dumps(study, indent=2) + '\n')


if __name__ == '__main__':
    main()
