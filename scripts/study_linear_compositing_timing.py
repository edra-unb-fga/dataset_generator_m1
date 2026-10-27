#!/usr/bin/env python3
"""Guarded, paired production-path timing of experimental linear compositing."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

from dataset_generator_m1.blender_runner import monitor
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.models import ExecutionConfig, GenerationProfile, SceneOcclusionConfig
from study_surface_2d import atomic_json, run_pool


def load_matrix(path):
    matrix = json.loads(Path(path).read_text())
    required = {'schema_version','config','image_size','measured_samples','warmups','repetitions','modes','execution','occlusion','guards','time_budget_seconds'}
    if set(matrix) != required or matrix['schema_version'] != 1:
        raise ValueError('Invalid timing-study matrix')
    if matrix['modes'] != ['legacy', 'linear-srgb'] or matrix['repetitions'] != 3 or matrix['warmups'] != 2:
        raise ValueError('Study requires two modes, two warmups and three repetitions')
    if not 2 <= matrix['measured_samples'] <= 20 or len(matrix['image_size']) != 2 or any(not 64 <= n <= 1280 for n in matrix['image_size']):
        raise ValueError('Invalid timing sample count or dimensions')
    if not math.isfinite(matrix['time_budget_seconds']) or not 0 < matrix['time_budget_seconds'] <= 900:
        raise ValueError('Timing budget must be positive and at most 15 minutes')
    guards = matrix['guards']
    if set(guards) != {'min_available_gib', 'rss_limit_gib', 'max_swap_out_mib'} or not all(math.isfinite(v) for v in guards.values()) or guards['min_available_gib'] < 2 or not 0 < guards['rss_limit_gib'] <= 10 or not 0 < guards['max_swap_out_mib'] <= 16:
        raise ValueError('Resource guards must be at least as strict as the saved study limits')
    SceneOcclusionConfig.model_validate(matrix['occlusion'])
    return matrix


def profile_for(base, matrix, mode, count):
    payload = base.profile.model_dump(mode='json')
    payload['run']['num_images'] = count
    payload['output']['image_size'] = matrix['image_size']
    payload['scene']['compositing'] = mode
    payload['scene']['occlusion'] = matrix['occlusion']
    payload['execution'] = ExecutionConfig.model_validate({**payload['execution'], **matrix['execution']}).model_dump(mode='json')
    profile = GenerationProfile.model_validate(payload)
    return base.model_copy(update={'profile': profile,
        'contract_hash': digest({'base': base.contract_hash, 'linear_compositing_timing_profile': payload}),
        'applied_overrides': {**base.applied_overrides, 'compositing_timing': {'mode':mode, 'samples':count}}})


def run_child(matrix, root):
    base = load_profile(matrix['config'])
    root.mkdir(parents=True, exist_ok=False)
    atomic_json(root/'matrix.json', matrix)
    atomic_json(root/'provenance.json', {'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'config_sha256':hashlib.sha256(Path(matrix['config']).read_bytes()).hexdigest(),
        'input_sources':base.source_hashes, 'software':software_identity(),
        'note':'Alternating-order single coordinator; two separately generated warmup outputs per cell. Measured scene slots repeat across repetitions.'})
    observations, records, reference = root/'local-observations.jsonl', [], None
    for repeat in range(matrix['repetitions']):
        order = matrix['modes'][repeat % 2:] + matrix['modes'][:repeat % 2]
        for mode in order:
            name=f'{repeat:02d}-{mode}'
            warm = profile_for(base, matrix, mode, matrix['warmups'])
            warm_summary, _, _, warm_prep, warm_generation, _, _ = run_pool(warm, root/f'warmup-{name}', observations)
            selected = profile_for(base, matrix, mode, matrix['measured_samples'])
            summary, inspection, policy, prep, elapsed, signature, rows = run_pool(selected, root/name, observations)
            if reference is None:
                reference = signature
            if reference != signature:
                raise RuntimeError('Paired geometry, annotations, and masks differ')
            row = {'repeat':repeat, 'mode':mode, 'pool':name, 'warmup_accepted':warm_summary['accepted_samples'],
                   'warmup_generation_seconds':warm_generation, 'warmup_preparation_seconds':warm_prep,
                   'accepted':summary['accepted_samples'], 'candidate_attempts':summary['candidate_attempts'],
                   'generation_seconds':elapsed, 'preparation_seconds':prep,
                   'images_per_second':summary['accepted_samples']/elapsed,
                   'prepared_images_per_second':summary['accepted_samples']/(elapsed+prep),
                   'content_signature':signature, 'resource_peaks':summary['resource_peaks'],
                   'unique_intents':len({(r['slot'], r['candidate_attempt']) for r in rows}),
                   'inspection':inspection['status'], 'execution':policy.as_dict()}
            records.append(row)
            atomic_json(root/'records.json',records)
            print(f'{name}: {row["images_per_second"]:.3f} accepted/s',flush=True)
    medians={mode:statistics.median(r['images_per_second'] for r in records if r['mode']==mode) for mode in matrix['modes']}
    pairs=[{'repeat':n,'legacy':next(r['images_per_second'] for r in records if r['repeat']==n and r['mode']=='legacy'),
            'linear':next(r['images_per_second'] for r in records if r['repeat']==n and r['mode']=='linear-srgb')} for n in range(matrix['repetitions'])]
    for pair in pairs:
        pair['linear_vs_legacy_percent']=(pair['linear']/pair['legacy']-1)*100
    result={'status':'complete','scope':'environment-local production-path 2D paired comparison; not a visual quality result',
            'samples_per_cell':matrix['measured_samples'], 'warmups_per_cell':matrix['warmups'],
            'repetitions':matrix['repetitions'], 'unique_scene_slots_per_mode':matrix['measured_samples'],
            'all_geometry_annotations_and_mask_signatures_equal':True, 'medians_images_per_second':medians,
            'median_paired_percent':statistics.median(p['linear_vs_legacy_percent'] for p in pairs),
            'paired_results':pairs,'records':records,
            'limitations':['Only four distinct measured scene slots repeat across the three repetitions.',
                           'Generation time includes pool writes; preparation is reported separately.',
                           'Only this machine and configured 640px scenario are measured; no hardware defaults inferred.']}
    atomic_json(root/'summary.json',result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix',default='experiments/planar/linear-compositing-timing.json')
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    matrix=load_matrix(args.matrix)
    if args.child:
        run_child(matrix,Path(args.output_dir))
        return
    root=Path(args.output_dir)
    root.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(args.matrix,root/'matrix-input.json')
    cmd=[sys.executable, str(Path(__file__).resolve()), '--matrix', str(Path(args.matrix).resolve()), '--output-dir', str((root/'study').resolve()), '--child']
    outcome=monitor([cmd],root,'timing',matrix['time_budget_seconds'],matrix['guards'])
    atomic_json(root/'guard-outcome.json',outcome)
    if outcome['status'] != 'complete':
        raise SystemExit(f"Timing study {outcome['status']}: {outcome['reason']}")
    print((root/'study'/'summary.json').read_text())


if __name__=='__main__':
    main()
