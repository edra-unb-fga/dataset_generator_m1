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
    if variant not in ('baseline', 'broad', 'soft'):
        raise ValueError('Unknown variant')
    for lamp in result if variant != 'baseline' else []:
        # Map the original preset ranges to candidate ranges at the same quantile.
        # Lamp kind/color and all other scene controls remain matched for attribution.
        if variant == 'broad':
            lamp['location'] = [lamp['location'][0] * 1.5, lamp['location'][1] * 1.5,
                                2.5 + (lamp['location'][2] - 2.0) * 1.5]
            lamp['power_w'] = 300 + (lamp['power_w'] - 300) * 700 / 900
            lamp['size_m'] = .8 + (lamp['size_m'] - .2) * 1.45 / 1.3
            lamp['spot_size_rad'] = 1.0 + (lamp['spot_size_rad'] - .6) * .9 / .6
        else:
            lamp['location'] = [lamp['location'][0], lamp['location'][1],
                                2.0 + (lamp['location'][2] - 2.0) * 1.5]
            lamp['power_w'] *= .8
            lamp['size_m'] = .5 + (lamp['size_m'] - .2) * 1.5 / 1.3
            lamp['spot_size_rad'] = .9 + (lamp['spot_size_rad'] - .6) * .9 / .6
        lamp['spot_blend'] = .5 + (lamp['spot_blend'] - .1) * .4 / .3
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
