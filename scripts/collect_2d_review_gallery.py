#!/usr/bin/env python3
"""Collect committed 2D study samples into a self-contained review manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def collect(study: Path, destination: Path) -> dict:
    study, destination = study.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError('Use a fresh review directory')
    records = json.loads((study / 'records.json').read_text())
    destination.mkdir(parents=True)
    images = []
    for record in records:
        pool = (study / record['pool']).resolve()
        if not pool.is_relative_to(study):
            raise ValueError('Pool escapes study directory')
        family, variant = record['family'], record['variant']
        profiles_file = study / (family + '-profiles.json')
        profiles = json.loads(profiles_file.read_text()) if profiles_file.exists() else None
        if profiles is not None:
            (destination / 'profiles').mkdir(exist_ok=True)
            shutil.copyfile(profiles_file, destination / 'profiles' / profiles_file.name)
        profile_record = profiles.get(variant, {}) if profiles else {}
        run = profile_record.get('profile', {}).get('run', {})
        record_summary = {key: record.get(key) for key in
                          ('family', 'variant', 'accepted', 'generation_seconds',
                           'images_per_second', 'signature')}
        for line in (pool / 'samples.jsonl').read_text().splitlines():
            sample = json.loads(line)
            source = (pool / sample['image_path']).resolve()
            if not source.is_relative_to(pool) or not source.is_file():
                raise ValueError('Sample image is missing or escapes its pool')
            name = f'{family}-{variant}-{sample["slot"]:04d}{source.suffix.lower()}'
            target = destination / 'images' / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            images.append({'path': 'images/' + name, 'engine': '2D', 'family': family,
                           'condition': variant, 'label': f'{family} · {variant} · slot {sample["slot"]}',
                           'metadata': {'image_sha256': digest, 'study_record': record_summary,
                                        'run_seed': run.get('seed'),
                                        'profile_file': 'profiles/' + profiles_file.name if profiles else None,
                                        'sample': sample}})
    # Adjacent cards show the same scene's baseline and candidate, not two
    # unrelated samples. Slot and family remain in each image's metadata.
    images.sort(key=lambda item: (item['family'], item['metadata']['sample']['slot'],
                                  item['condition'] != 'baseline', item['condition']))
    result = {'title': '2D scene candidate review', 'images': images}
    (destination / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    value = collect(args.study, args.destination)
    print(f'Collected {len(value["images"])} committed images')


if __name__ == '__main__':
    main()
