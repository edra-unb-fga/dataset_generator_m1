"""Collect completed paired directional-shade pools for the existing review gallery."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def collect(pairs, destination):
    destination = destination.resolve()
    families = [family for family, _ in pairs]
    if len(set(families)) != len(families) or any(family not in {'landing-pad', 'landing', 'manometro'} for family in families):
        raise ValueError('Expected unique maintained family names')
    if destination.exists():
        raise FileExistsError('Use a fresh destination')
    destination.mkdir(parents=True)
    images = []
    for family, root in pairs:
        root = root.resolve()
        result = json.loads((root/'result.json').read_text())
        study = root/'study'
        summary = json.loads((study/'summary.json').read_text())
        if result['status'] != 'complete' or summary['status'] != 'complete':
            raise ValueError(f'Incomplete study: {root}')
        signatures = summary['signatures']
        if set(signatures) != {'baseline', 'natural-directional'} or len(set(signatures.values())) != 1:
            raise ValueError(f'Paired signatures do not match: {root}')
        (destination/'profiles').mkdir(exist_ok=True)
        profile_name = family + '-study.json'
        shutil.copyfile(study/'study.json', destination/'profiles'/profile_name)
        for condition in ('baseline', 'natural-directional'):
            pool = (study/condition).resolve()
            for line in (pool/'samples.jsonl').read_text().splitlines():
                sample = json.loads(line)
                source = (pool/sample['image_path']).resolve()
                if not source.is_relative_to(pool) or not source.is_file():
                    raise ValueError(f'Invalid sample image: {source}')
                name = f'{family}-{sample["slot"]:04d}-{condition}{source.suffix.lower()}'
                target = destination/'images'/name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(source, target)
                images.append({'path':'images/'+name, 'engine':'2D', 'family':family, 'condition':condition,
                    'label':f'{family} · slot {sample["slot"]} · {condition}',
                    'metadata':{'image_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                        'signature':signatures[condition], 'profile_file':'profiles/'+profile_name,
                        'sample':sample}})
    images.sort(key=lambda item:(item['family'], item['metadata']['sample']['slot'], item['condition'] != 'baseline'))
    manifest = {'title':'Directional shade natural-sampling review', 'images':images}
    (destination/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return len(images)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', nargs=2, action='append', required=True, metavar=('FAMILY','PATH'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(f'Collected {collect([(family, Path(path)) for family, path in args.study], args.output_dir)} images')


if __name__ == '__main__':
    main()
