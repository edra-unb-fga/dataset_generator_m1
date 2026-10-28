"""Paired, budgeted Blender surface performance confirmation from a frozen matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
from pathlib import Path

import numpy as np

from dataset_generator_m1.blender_pilot import (atomic_json, completed_outputs, digest,
    digest_file, export_coco, load_config, prepare, run_study)
from dataset_generator_m1.ownership import CoordinatorLease
from dataset_generator_m1.surface_study import BudgetLedger, BudgetPolicy


def evidence(rows):
    """Fingerprint geometry, acceptance, and exact mask values independent of file encoding."""
    result = []
    for job, path, row in sorted(rows, key=lambda item: item[0]['scene_index']):
        item = {'scene_index': job['scene_index'], 'reference_scene_index': job['reference_scene_index'],
                'seed': job['seed'], 'scene': job['scene'], 'ground_index': job['ground_index'],
                'status': row['status'], 'attempts': [{k: a.get(k) for k in ('attempt', 'support', 'rejection')}
                                                       for a in row['attempts']]}
        if row['status'] == 'accepted':
            with np.load(path/'masks.npz', allow_pickle=False) as masks:
                item['masks'] = {key: {'shape': list(masks[key].shape), 'dtype': str(masks[key].dtype),
                    'sha256': hashlib.sha256(np.ascontiguousarray(masks[key]).tobytes()).hexdigest()}
                    for key in sorted(masks.files)}
        result.append(item)
    return digest(result)


def checked_phase(cell, study, ids, blenderproc, install):
    before = len(json.loads((cell/'runs.json').read_text())) if (cell/'runs.json').exists() else 0
    outcome = run_study(cell, blenderproc, install, job_ids=ids)
    runs = json.loads((cell/'runs.json').read_text())[before:]
    if outcome['status'] != 'complete' or len(runs) != 2 or runs[0]['phase'].split('-')[0] != 'probe' or runs[1]['phase'].split('-')[0] != 'run':
        raise RuntimeError(f'Incomplete command in {cell}: {outcome}')
    rows = [r for r in completed_outputs(cell, study) if r[0]['id'] in ids]
    if len(rows) != len(ids) or any(row['status'] != 'accepted' for _, _, row in rows):
        raise RuntimeError(f'Incomplete or rejected scenes in {cell}')
    return runs, rows


def validate_benchmark(value):
    if not isinstance(value, dict) or set(value) != {'warmups', 'measured', 'repetitions', 'resolutions'}:
        raise ValueError('Invalid benchmark fields')
    for key, lower, upper in (('warmups', 1, 5), ('measured', 1, 95), ('repetitions', 1, 10)):
        if type(value[key]) is not int or not lower <= value[key] <= upper:
            raise ValueError(f'Invalid benchmark {key}')
    if value['warmups'] + value['measured'] > 100:
        raise ValueError('Benchmark scene count exceeds pilot limit')
    sizes = value['resolutions']
    if (not isinstance(sizes, list) or not sizes or any(not isinstance(size, list) or len(size) != 2 or
            any(type(n) is not int or not 64 <= n <= 2048 for n in size) for size in sizes) or
            len({tuple(size) for size in sizes}) != len(sizes)):
        raise ValueError('Invalid benchmark resolutions')
    return value


def phase_ids(benchmark, variant):
    warmups = benchmark['warmups']
    return ([f'{i:03d}-{variant}-fast' for i in range(warmups)],
            [f'{i:03d}-{variant}-fast' for i in range(warmups, warmups + benchmark['measured'])])


def validate_study_id(value):
    if not isinstance(value, str) or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value) is None:
        raise ValueError('Study ID must be a lowercase alphanumeric/hyphen slug of at most 64 characters')
    return value


def run(config, matrix_file, output_dir, blenderproc, install, study_id='performance'):
    study_id = validate_study_id(study_id)
    root, matrix_file = Path(output_dir).resolve(), Path(matrix_file).resolve()
    config = Path(config).resolve()
    matrix = json.loads(matrix_file.read_text())
    benchmark = validate_benchmark(matrix['benchmark'])
    policy = BudgetPolicy.model_validate(matrix['budget'])
    base = load_config(config).model_dump(mode='json')
    driver = Path(__file__).resolve()
    with CoordinatorLease(root):
        performance = root/study_id
        if performance.exists():
            raise ValueError('Performance evidence already exists; do not retry or overwrite cells')
        design = {'matrix': matrix, 'matrix_sha256': digest_file(matrix_file)}
        if (root/'design.json').exists() and json.loads((root/'design.json').read_text()) != design:
            raise ValueError('Frozen study matrix changed')
        atomic_json(root/'design.json', design)
        ledger = BudgetLedger(root, policy)
        performance.mkdir()
        shutil.copyfile(driver, performance/'driver-source.py')
        atomic_json(performance/'matrix.json', matrix)
        atomic_json(performance/'provenance.json', {'study_id': study_id, 'matrix_sha256': design['matrix_sha256'],
            'driver_sha256': digest_file(driver), 'config_sha256': digest_file(config),
            'resolved_config': base, 'blenderproc': str(Path(blenderproc).resolve()),
            'blender_install_path': str(Path(install).resolve()),
            'benchmark': benchmark, 'timing': 'Measured render command only; probes and warmups charged separately.'})
        records, pairs = [], {}
        try:
            for resolution in benchmark['resolutions']:
                size = f'{resolution[0]}x{resolution[1]}'
                for repeat in range(benchmark['repetitions']):
                    variants = ('core', 'wear') if repeat % 2 == 0 else ('wear', 'core')
                    for variant in variants:
                        name = f'{study_id}-{size}-{repeat:02d}-{variant}'
                        if any(e['name'] == name for e in ledger.value['entries']):
                            raise ValueError('Cell already reserved')
                        allowance = ledger.allowance('final')
                        if allowance <= 0:
                            raise ValueError('Budget prevents further performance work')
                        cell = performance/'cells'/name
                        payload = dict(base)
                        payload.update(resolution=resolution, scenes=benchmark['warmups'] + benchmark['measured'], quality_treatments=[],
                            study_seconds=min(allowance, base['study_seconds']),
                            treatments=[dict(matrix['recipes'][variant]['treatment'], id=variant)])
                        config_path = performance/'configs'/f'{name}.json'
                        atomic_json(config_path, payload)
                        study = prepare(config_path, cell)
                        ledger.reserve(name, 'final')
                        try:
                            warm_ids, measured_ids = phase_ids(benchmark, variant)
                            warm, _ = checked_phase(cell, study, warm_ids, blenderproc, install)
                            measured, rows = checked_phase(cell, study, measured_ids, blenderproc, install)
                            execution = json.loads((cell/'execution.json').read_text())['selection']
                            selected_workers = execution['settings']['workers']
                            if measured[1]['workers'] != min(selected_workers, len(measured_ids)) or measured[1]['command_seconds'] <= 0:
                                raise ValueError('Invalid measured worker count or timing')
                            signature = evidence(rows)
                            pair = (size, repeat)
                            if pair in pairs and pairs[pair] != signature:
                                raise ValueError('Paired acceptance, geometry, or exact masks differ')
                            pairs[pair] = signature
                            record = {'cell': name, 'resolution': resolution, 'repeat': repeat, 'variant': variant,
                                'identity': study['identity'], 'source_fingerprints': study['contract']['harness_sources'],
                                'accepted': len(rows), 'signature': signature, 'execution': execution,
                                'selected_workers': selected_workers, 'measured_workers': measured[1]['workers'],
                                'warmup_probe': warm[0], 'warmup_command': warm[1],
                                'measured_probe': measured[0], 'measured_command': measured[1],
                                'images_per_second': len(rows)/measured[1]['command_seconds']}
                            if repeat == 0:
                                record['export'] = export_coco(cell)
                            records.append(record)
                            atomic_json(performance/'records.json', records)
                            print(f'{name}: {record["images_per_second"]:.3f} images/s', flush=True)
                        finally:
                            if (cell/'runs.json').exists():
                                ledger.settle(name, json.loads((cell/'runs.json').read_text()), evidence_identity=study['identity'])
            medians = [{'resolution': size, 'variant': variant,
                'median_images_per_second': statistics.median(r['images_per_second'] for r in records
                    if r['resolution'] == size and r['variant'] == variant)}
                for size in benchmark['resolutions'] for variant in ('core', 'wear')]
            result = {'study_id': study_id, 'status': 'complete', 'checks': {'paired_geometry_acceptance_masks_equal': True,
                'all_measured_accepted': True, 'resolved_worker_counts_match': True}, 'records': records, 'medians': medians,
                'budget_used_seconds': ledger.used(), 'limitations': ['Environment-local confirmation; no cross-machine speed claim.']}
            atomic_json(performance/'summary.json', result)
            return result
        except BaseException as error:
            atomic_json(performance/'summary.json', {'study_id': study_id, 'status': 'failed', 'error': str(error),
                'records': records, 'budget_used_seconds': ledger.used()})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'matrix', 'output-dir', 'blenderproc', 'blender-install-path'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--study-id', default='performance')
    args = parser.parse_args()
    run(args.config, args.matrix, args.output_dir, args.blenderproc, args.blender_install_path, args.study_id)


if __name__ == '__main__':
    main()
