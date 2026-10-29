"""Run paired 2D foreground-context variants and generate an offline visual report.

Use separate fresh output directories for development and reserved phases; review
and select settings during development before running the reserved seed.
"""
from __future__ import annotations

import argparse
import html
import hashlib
import re
import json
from pathlib import Path
import shutil

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.models import ExecutionConfig, ForegroundContextConfig, GenerationProfile
from study_surface_2d import atomic_json, run_pool

DEFAULT_MATRIX = Path(__file__).resolve().parents[1] / 'experiments/blenderproc/studies/foreground-context.json'


def load_matrix(path):
    raw = Path(path).read_bytes()
    matrix = json.loads(raw)
    if set(matrix) != {'schema_version', 'seeds', 'variants'} or matrix['schema_version'] != 1:
        raise ValueError('Invalid context study matrix fields or schema version')
    seeds, variants = matrix['seeds'], matrix['variants']
    if (not isinstance(seeds, dict) or set(seeds) != {'development', 'reserved'}
            or any(type(seed) is not int or seed < 0 for seed in seeds.values())
            or seeds['development'] == seeds['reserved']):
        raise ValueError('Matrix needs distinct nonnegative development and reserved seeds')
    if not isinstance(variants, dict) or len(variants) < 2 or list(variants)[0] != 'baseline' or variants['baseline'] is not None:
        raise ValueError('Matrix needs baseline first, with null context, and at least one variant')
    for name, context in variants.items():
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
            raise ValueError('Invalid variant name')
        if name != 'baseline':
            if not isinstance(context, dict):
                raise ValueError('Treatment context must be an object')
            # Require every setting explicitly: matrix captures all candidate parameters.
            if set(context) != {'probability', 'strength', 'radius_fraction', 'max_brightness_shift', 'max_color_shift'}:
                raise ValueError('Treatment must specify all context settings')
            ForegroundContextConfig.model_validate(context)
    return matrix, raw, hashlib.sha256(raw).hexdigest()


def profile_for(base, variant, phase, count, matrix, execution=None):
    payload = base.profile.model_dump(mode='json')
    payload['run']['seed'] = matrix['seeds'][phase]
    payload['run']['num_images'] = count
    payload['scene']['foreground_context'] = matrix['variants'][variant]
    if execution is not None:
        payload['execution'] = execution.model_dump(mode='json')
    profile = GenerationProfile.model_validate(payload)
    return base.model_copy(update={'profile': profile,
        'contract_hash': digest({'base': base.contract_hash, 'context_study': payload}),
        'applied_overrides': {**base.applied_overrides, 'context_study': {'phase': phase, 'variant': variant}}})


def report(root, phase, rows, signatures, matrix):
    columns = list(matrix['variants'])
    tables = []
    slots = sorted(set.intersection(*(set(rows[v]) for v in columns)))
    for slot in slots:
        cells = []
        for variant in columns:
            row = rows[variant][slot]
            path = (Path(variant) / row['image_path']).as_posix()
            cells.append(f'<td><img loading="lazy" src="{html.escape(path, quote=True)}" alt="{html.escape(variant)} slot {slot}"><br>{html.escape(variant)}</td>')
        tables.append(f'<tr><th>Slot {slot}</th>' + ''.join(cells) + '</tr>')
    document = '''<!doctype html><html><head><meta charset="utf-8"><title>Foreground context study</title>
<style>body{font:16px sans-serif;margin:2rem;max-width:1500px}table{border-collapse:collapse}td,th{padding:8px;vertical-align:top}img{width:100%;max-width:400px}td{width:30%}</style></head><body>'''
    document += f"<h1>Foreground context: {html.escape(phase)}</h1><p>Paired synthetic scenes, seed {matrix['seeds'][phase]}. Inspect appearance, readability and masks; these images do not establish realism or detector benefit. Broad settings can substantially change colours.</p>"
    document += '<p>Geometry, annotations and mask evidence match across variants: ' + html.escape(str(len(set(signatures.values())) == 1)) + f'. Paired slots: {len(slots)}.</p><table>' + ''.join(tables) + '</table></body></html>'
    (root/'report.html').write_text(document, encoding='utf-8')


def run(config, output, phase, count, matrix_path=DEFAULT_MATRIX, execution_policy=None):
    matrix, matrix_bytes, matrix_hash = load_matrix(matrix_path)
    if phase not in matrix['seeds']:
        raise ValueError('Unknown study phase')
    if not 1 <= count <= 100:
        raise ValueError('samples must be between 1 and 100')
    root = Path(output).resolve()
    if root.exists():
        raise ValueError('Use a fresh output directory')
    base = load_profile(Path(config).resolve())
    execution = ExecutionConfig.model_validate(json.loads(Path(execution_policy).read_text())) if execution_policy else None
    profiles = {v: profile_for(base, v, phase, count, matrix, execution) for v in matrix['variants']}
    for current in profiles.values():
        plan_execution(current)
    root.mkdir(parents=True)
    shutil.copyfile(__file__, root/'driver-source.py')
    (root/'matrix.json').write_bytes(matrix_bytes)
    atomic_json(root/'study.json', {'schema_version': 1, 'phase': phase, 'seed': matrix['seeds'][phase],
        'samples': count, 'matrix_sha256': matrix_hash, 'matrix': matrix, 'source_hashes': base.source_hashes,
        'effective_profiles': {name: current.profile.model_dump(mode='json') for name, current in profiles.items()},
        'software': software_identity(), 'limitations': ['Synthetic evidence only; no realism or detector benefit is established.',
            'Reserved seed uses the same asset catalog and does not establish asset holdout.']})
    rows, signatures = {}, {}
    for name, current in profiles.items():
        summary, inspection, plan, prep, wall, signature, samples = run_pool(current, root/name, root/'local-observations.jsonl')
        signatures[name] = signature
        rows[name] = {row['slot']: row for row in samples}
        atomic_json(root/f'{name}-result.json', {'accepted': summary['accepted_samples'],
            'inspection': inspection['status'], 'signature': signature, 'execution': plan.as_dict(),
            'preparation_seconds': prep, 'generation_seconds': wall})
        if name != 'baseline' and signature != signatures['baseline']:
            raise RuntimeError(f'{name} changed paired geometry, annotations, or masks')
    report(root, phase, rows, signatures, matrix)
    atomic_json(root/'summary.json', {'status': 'complete', 'phase': phase, 'signatures': signatures,
        'paired_slots': sorted(set.intersection(*(set(rows[v]) for v in matrix['variants']))), 'report': 'report.html'})
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--phase', choices=('development', 'reserved'), required=True)
    parser.add_argument('--samples', type=int, default=12)
    parser.add_argument('--matrix', default=DEFAULT_MATRIX)
    parser.add_argument('--execution-policy', help='JSON ExecutionConfig override; recorded in the study')
    args = parser.parse_args()
    print(run(args.config, args.output_dir, args.phase, args.samples, args.matrix, args.execution_policy))


if __name__ == '__main__':
    main()
