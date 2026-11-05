#!/usr/bin/env python3
"""Collect accepted BlenderProc render results into a portable review manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def collect(results: Path, destination: Path) -> dict:
    results, destination = results.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError('Use a fresh review directory')
    destination.mkdir(parents=True)
    images = []
    for file in sorted(results.glob('*/scenes/*/result.json')):
        result = json.loads(file.read_text())
        if result.get('status') != 'accepted':
            continue
        source = file.parent / 'rgb.png'
        if not source.is_file():
            raise ValueError(f'Accepted result is missing its image: {file}')
        job = result['job']
        batch, job_id = file.parents[2].name, file.parent.name
        name = f'{batch}-{job_id}.png'
        target = destination / 'images' / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        declared = result.get('files', {}).get('rgb.png')
        expected = declared.get('sha256') if isinstance(declared, dict) else declared
        if not isinstance(expected, str) or expected != digest:
            raise ValueError(f'Image checksum missing or mismatched: {file}')
        metadata = {key: result[key] for key in ('identity', 'job', 'attempts', 'device',
                    'intrinsics_K_before_distortion', 'camera_distance_metres', 'renderer_settings',
                    'surface_diagnostics', 'ground_diagnostics', 'environment_geometry_diagnostics',
                    'files') if key in result}
        metadata['image_sha256'] = digest
        images.append({'path': 'images/' + name, 'engine': 'BlenderProc 3D', 'family': 'landing-pad',
                       'condition': job.get('environment_geometry', 'unknown'),
                       'label': f'{batch} · {job_id}', 'metadata': metadata})
    result = {'title': '3D scene candidate review', 'images': images}
    (destination / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    value = collect(args.results, args.destination)
    print(f'Collected {len(value["images"])} accepted images')


if __name__ == '__main__':
    main()
