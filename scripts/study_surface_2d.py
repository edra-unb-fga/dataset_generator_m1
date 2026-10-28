"""Paired production 2D surface study with saved recipes and external execution policy.

Warmups are separate valid pools, not part of measured throughput. Repetitions reuse
scene seeds and rotate recipe order. Cross-engine wear algorithms and map seeds can
be compared, but normal 2D effects retain their independently derived stream seeds.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import statistics
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.evaluation_io import prepare_dataset
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.generator import GenerationOptions, generate_pool
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.inspection import inspect_pool
from dataset_generator_m1.models import (EnvironmentalShadeConfig, ExecutionConfig,
    GenerationProfile, SceneInline, SurfaceWearConfig)
from dataset_generator_m1.preparation import PreparationRequest, prepare_generation


class Variant(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    wear: SurfaceWearConfig | None
    shade: EnvironmentalShadeConfig | None = None
    repetitions: int | None = Field(default=None, ge=1, le=5)


class Matrix(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1]
    samples: int = Field(ge=1, le=100)
    warmups: int = Field(ge=0, le=5)
    repetitions: int = Field(ge=1, le=5)
    resolutions: tuple[tuple[int, int], ...]
    shared_scene: SceneInline = Field(default_factory=SceneInline)
    prepare_evaluation: bool = True
    variants: tuple[Variant, ...]

    @model_validator(mode='after')
    def validate_matrix(self):
        if not self.resolutions or len(set(self.resolutions)) != len(self.resolutions):
            raise ValueError('Resolution choices must be nonempty and unique')
        if any(min(size) < 1 or max(size) > 4096 for size in self.resolutions):
            raise ValueError('Study dimensions must be positive and at most4096')
        names = [v.name for v in self.variants]
        if not names or len(names) != len(set(names)):
            raise ValueError('Study variants must be nonempty and uniquely named')
        if self.shared_scene.lighting is not None and self.shared_scene.lighting.shade is not None:
            raise ValueError('Configure shade per variant, not on shared_scene')
        if any((v.repetitions or self.repetitions) > self.repetitions for v in self.variants):
            raise ValueError('Variant repetitions cannot exceed matrix repetitions')
        return self


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def merge(base, update):
    result = copy.deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def cell_profile(base, matrix, variant, resolution, count, policy):
    payload = base.profile.model_dump(mode='json')
    payload['scene'] = merge(payload['scene'], matrix.shared_scene.model_dump(mode='json', exclude_none=True))
    lighting = payload['scene'].get('lighting')
    if variant.shade is not None:
        if lighting is None:
            # A shade experiment cannot silently introduce gain/gradient/tint too.
            lighting = {'probability': 0, 'gain': [1, 1], 'gradient': [0, 0], 'tint': 0}
        payload['scene']['lighting'] = {**lighting, 'shade': variant.shade.model_dump(mode='json')}
    elif lighting is not None:
        payload['scene']['lighting'] = {k: v for k, v in lighting.items() if k != 'shade'}
    # Keep every unrelated appearance transform, but replace existing local wear.
    payload['appearance']['foreground'] = [v for v in payload['appearance']['foreground'] if v['type'] != 'SurfaceWear']
    if variant.wear is not None:
        payload['appearance']['foreground'].append({'id': 'shared-wear', 'type': 'SurfaceWear',
            'probability': 1., 'params': variant.wear.model_dump(mode='json')})
    payload['run']['num_images'] = count
    payload['output']['image_size'] = list(resolution)
    payload['execution'] = policy.model_dump(mode='json')
    profile = GenerationProfile.model_validate(payload)
    return base.model_copy(update={'profile': profile,
        'contract_hash': digest({'base': base.contract_hash, 'surface_study_profile': payload}),
        'applied_overrides': {**base.applied_overrides, 'surface_study': {'variant': variant.name,
            'resolution': list(resolution), 'samples': count, 'execution': policy.model_dump(mode='json')}}})


def pool_evidence(pool):
    rows = [json.loads(line) for line in (pool/'samples.jsonl').read_text().splitlines() if line]
    content = [{'slot': row['slot'], 'candidate_attempt': row['candidate_attempt'],
        'geometry': row['geometry_signature'], 'annotations': row['annotations'],
        'masks': {key: value for key, value in row['mask_evidence'].items() if key != 'path'}} for row in rows]
    return digest(content), rows


def run_pool(current, pool, observations, *, acknowledged_codes=()):
    plan = plan_execution(current)
    started = perf_counter()
    prepared = prepare_generation(PreparationRequest(current, pool, plan.workers, observations))
    preparation_seconds = perf_counter()-started
    started = perf_counter()
    required=set(prepared.preflight['required_acknowledgements'])
    receipt=None
    if required and required.issubset(set(acknowledged_codes)):
        from dataset_generator_m1.preflight import confirm_preflight
        receipt=pool.parent/(pool.name+'-preflight-receipt.json')
        confirm_preflight(prepared.preflight,receipt)
    summary = generate_pool(current, pool, GenerationOptions(display='quiet', output_format='json', prepared=prepared, receipt_path=receipt))
    generation_seconds = perf_counter()-started
    inspection = inspect_pool(pool)
    if (summary['status'] != 'complete' or inspection['status'] != 'valid' or
            summary['accepted_samples'] != current.profile.run.num_images):
        raise RuntimeError(f'Incomplete or invalid surface study pool: {pool}')
    signature, rows = pool_evidence(pool)
    return summary, inspection, plan, preparation_seconds, generation_seconds, signature, rows


def run_study(config, matrix_file, output_dir, execution_policy=None):
    config, matrix_file, root = Path(config).resolve(), Path(matrix_file).resolve(), Path(output_dir).resolve()
    matrix = Matrix.model_validate(json.loads(matrix_file.read_text()))
    base = load_profile(config)
    raw_policy = json.loads(Path(execution_policy).read_text()) if execution_policy is not None else {}
    policy = ExecutionConfig.model_validate({**base.profile.execution.model_dump(mode='json'), **raw_policy})
    if root.exists():
        raise ValueError('Use a fresh study output directory')
    # Validate all resolved candidates before creating any output.
    for resolution in matrix.resolutions:
        for variant in matrix.variants:
            plan_execution(cell_profile(base, matrix, variant, resolution, matrix.samples, policy))
    root.mkdir(parents=True)
    shutil.copyfile(__file__, root/'driver-source.py')
    atomic_json(root/'matrix.json', matrix.model_dump(mode='json'))
    atomic_json(root/'execution-policy.json', policy.model_dump(mode='json'))
    atomic_json(root/'provenance.json', {'schema_version': 1, 'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'matrix_sha256': hashlib.sha256(matrix_file.read_bytes()).hexdigest(),
        'input_config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(), 'input_sources': base.source_hashes,
        'execution_policy_sha256': digest(raw_policy), 'software': software_identity(),
        'note': 'Separate production warmup pools; coordinator remains alive between cells. Rotated within each resolution/repetition.'})
    observations, records, references = root/'local-observations.jsonl', [], {}
    for resolution in matrix.resolutions:
        size = f'{resolution[0]}x{resolution[1]}'
        for repeat in range(matrix.repetitions):
            variants = list(matrix.variants)
            variants = variants[repeat % len(variants):]+variants[:repeat % len(variants)]
            for variant in variants:
                if repeat >= (variant.repetitions or matrix.repetitions):
                    continue
                name = f'{size}-{repeat:02d}-{variant.name}'
                cell = root/name
                current = cell_profile(base, matrix, variant, resolution, matrix.samples, policy)
                atomic_json(root/'progress.json', {'status': 'running', 'cell': name, 'completed': len(records)})
                warmup = None
                if matrix.warmups:
                    warm = cell_profile(base, matrix, variant, resolution, matrix.warmups, policy)
                    warm_summary, _, _, prep, wall, _, _ = run_pool(warm, root/f'warmup-{name}', observations)
                    warmup = {'accepted': warm_summary['accepted_samples'], 'preparation_seconds': prep, 'generation_seconds': wall}
                summary, inspection, plan, prep, wall, signature, samples = run_pool(current, cell, observations)
                if size not in references:
                    references[size] = signature
                if references[size] != signature:
                    raise RuntimeError('Appearance treatment changed paired geometry/annotations/full-visible masks')
                row = {'resolution': list(resolution), 'repeat': repeat, 'variant': variant.name,
                    'pool': cell.relative_to(root).as_posix(), 'accepted': summary['accepted_samples'],
                    'candidate_attempts': summary['candidate_attempts'], 'inspection': inspection['status'],
                    'content_signature': signature, 'generation_seconds': wall, 'preparation_seconds': prep,
                    'images_per_second': summary['accepted_samples']/wall,
                    'prepared_command_images_per_second': summary['accepted_samples']/(prep+wall),
                    'active_images_per_second': summary['throughput_images_per_second'],
                    'stage_work': summary['stage_timings'], 'resource_peaks': summary['resource_peaks'],
                    'execution': plan.as_dict(), 'warmup': warmup,
                    'unique_measured_scene_intents': len({(r['slot'], r['candidate_attempt']) for r in samples}),
                    'scene_effects': [r.get('scene_effects') for r in samples],
                    'wear_effect_traces': [[t for t in r.get('appearance_effects', []) if t.get('type') == 'SurfaceWear'] for r in samples]}
                if repeat == 0 and matrix.prepare_evaluation:
                    manifest = root/f'evaluate-{name}.json'
                    atomic_json(manifest, {'schema_version': 1, 'format': 'pool', 'domain': 'synthetic',
                        'role': 'development', 'source': cell.relative_to(root).as_posix(), 'annotation_semantics': 'visible'})
                    evaluation = prepare_dataset(manifest, root/f'evaluation-{name}')
                    row['evaluation'] = {'path': f'evaluation-{name}/dataset.json', 'status': evaluation['status'],
                        'dataset_sha256': evaluation['dataset_sha256'], 'images': len(evaluation['ground_truth']['images']),
                        'annotations': len(evaluation['ground_truth']['annotations'])}
                records.append(row)
                atomic_json(root/'records.json', records)
                print(f'{name}: {row["images_per_second"]:.3f} accepted images/s', flush=True)
    medians = []
    for resolution in matrix.resolutions:
        for variant in matrix.variants:
            rows = [r for r in records if r['resolution'] == list(resolution) and r['variant'] == variant.name]
            medians.append({'resolution': list(resolution), 'variant': variant.name, 'repetitions': len(rows),
                'low_sample': len(rows) < 3 or matrix.samples < 20,
                'median_images_per_second': statistics.median(r['images_per_second'] for r in rows),
                'minimum_images_per_second': min(r['images_per_second'] for r in rows),
                'maximum_images_per_second': max(r['images_per_second'] for r in rows)})
    result = {'schema_version': 1, 'status': 'complete', 'scope': 'Production 2D environment-local paired appearance study',
        'all_content_signatures_equal': True, 'samples': matrix.samples, 'warmups': matrix.warmups,
        'matrix': matrix.model_dump(mode='json'), 'records': records, 'medians': medians,
        'limitations': ['Independent 2D effect streams are not identical to 3D map-preparation seeds.',
            'Synthetic development evidence does not establish real-image or detector benefit.',
            'Generation timing includes pool work, writes and QA; preparation and evaluator copying are separate.']}
    atomic_json(root/'summary.json', result)
    atomic_json(root/'progress.json', {'status': 'complete', 'completed': len(records)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--matrix', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--execution-policy')
    args = parser.parse_args()
    run_study(args.config, args.matrix, args.output_dir, args.execution_policy)


if __name__ == '__main__':
    main()
