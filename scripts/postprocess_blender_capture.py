#!/usr/bin/env python3
"""Apply a selected final-image appearance profile to verified BlenderProc scenes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image

from dataset_generator_m1.blender_pilot import completed_outputs, digest_file, load_study
from dataset_generator_m1.config import load_appearance_profile
from dataset_generator_m1.filters import apply_pipeline_traced, backend_version
from dataset_generator_m1.identities import digest


def postprocess(input_dir, output_dir, profile, seed):
    source = Path(input_dir).resolve()
    output = Path(output_dir).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Output must be separate from the source study')
    if seed < 0:
        raise ValueError('Seed must be nonnegative')
    study = load_study(source)
    completed = completed_outputs(source, study)
    accepted = [(job, path, row) for job, path, row in completed if row['status'] == 'accepted']
    if not accepted:
        raise ValueError('No verified accepted source scenes')
    ids = [job['id'] for job, _, _ in accepted]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) or Path(i).name != i or i in ('.', '..') for i in ids):
        raise ValueError('Duplicate or unsafe source job identifiers')
    appearance = load_appearance_profile(profile, source/'study.json')
    specs = [s.model_dump(mode='json') for s in appearance.final]
    identity = digest({'schema_version': 1, 'study_identity': study['identity'], 'profile': specs,
                       'seed': seed, 'backend_version': backend_version(),
                       'sources': [{'id': job['id'], 'files': row['files']} for job, _, row in accepted]})
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for job, path, row in accepted:
        sample_seed = int.from_bytes(hashlib.sha256(f"{seed}:{study['identity']}:{job['id']}".encode()).digest()[:4], 'big')
        image = np.asarray(Image.open(path/'rgb.png').convert('RGB'))
        transformed, trace = apply_pipeline_traced(image, appearance.final, sample_seed, 'final')
        target = output/'scenes'/job['id']
        target.mkdir(parents=True)
        Image.fromarray(transformed).save(target/'rgb.png')
        shutil.copyfile(path/'masks.npz', target/'masks.npz')
        if digest_file(target/'masks.npz') != row['files']['masks.npz']:
            raise ValueError('Copied mask differs from verified source')
        records.append({'job_id': job['id'], 'source_rgb_sha256': row['files']['rgb.png'],
                        'source_masks_sha256': row['files']['masks.npz'], 'seed': sample_seed,
                        'image': f"scenes/{job['id']}/rgb.png", 'image_sha256': digest_file(target/'rgb.png'),
                        'masks': f"scenes/{job['id']}/masks.npz", 'trace': [t.__dict__ for t in trace]})
    manifest = {'schema_version': 1, 'identity': identity, 'source_study_identity': study['identity'],
                'capture_profile': profile, 'resolved_final_effects': specs, 'seed': seed,
                'backend_version': backend_version(), 'images': records,
                'source_accepted_count': len(accepted), 'source_completed_count': len(completed),
                'annotation_note': 'Masks are unmodified geometric source evidence, not optical blur masks.',
                'limitations': 'Only completed accepted source scenes are included; this is not a new BlenderProc study or export.'}
    (output/'capture-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    result = postprocess(args.input_dir, args.output_dir, args.profile, args.seed)
    print(json.dumps({'identity': result['identity'], 'images': len(result['images']), 'output': args.output_dir}))


if __name__ == '__main__':
    main()
