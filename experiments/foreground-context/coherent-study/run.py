"""Guarded production comparison of standard and opt-in coherent profiles."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import psutil
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

from dataset_generator_m1.blender_runner import monitor
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.identities import digest, software_identity
from dataset_generator_m1.models import ExecutionConfig, GenerationProfile
from guarded_effect_combinations import Policy, resolve_guards
from study_surface_2d import atomic_json, run_pool

FAMILIES = ('landing-pad', 'landing', 'manometro')
ACKNOWLEDGED = {'REALISTIC_HEAVY_COST', 'UNCALIBRATED_COHERENT_APPEARANCE',
    'UNCALIBRATED_COHERENT_SCENE', 'EXPERIMENTAL_SCENE_LIGHTING_UNCALIBRATED',
    'EXPERIMENTAL_FOREGROUND_CONTEXT_UNCALIBRATED'}
DEFAULT_POLICY = ROOT / 'experiments/foreground-context/local-cpu-policy.json'


def profiles(root, family, treatment, samples, seed, size):
    """Save source composers and return resolved, paired production profiles."""
    source = ROOT / f'examples/configs/{family}_minimal.yaml'
    raw = yaml.safe_load(source.read_text())
    result = {}
    for variant in ('baseline', 'candidate'):
        composer = dict(raw)
        if variant == 'candidate':
            composer['scene'] = 'builtin:scene/coherent-varied' if treatment == 'coherent-varied-manometro' else f'builtin:scene/{treatment}'
            appearance = 'coherent-refined' if treatment == 'coherent-directional' else treatment
            composer['appearance'] = {'preset': f'builtin:appearance/{appearance}'}
        path = root / f'{family}-{variant}.yaml'
        path.write_text(yaml.safe_dump(composer, sort_keys=False))
        base = load_profile(path)
        values = base.profile.model_dump(mode='json')
        values['run'].update(seed=seed, num_images=samples)
        values['output']['image_size'] = [size, size]
        values['execution'] = ExecutionConfig(workers=1, native_threads=1).model_dump(mode='json')
        profile = GenerationProfile.model_validate(values)
        result[variant] = base.model_copy(update={'profile': profile,
            'contract_hash': digest({'base': base.contract_hash, 'study': values}),
            'applied_overrides': {'study': {'seed': seed, 'samples': samples,
                'size': [size, size], 'workers': 1}}})
    return result


def worker(root, families, treatment, samples, seed, size):
    records = []
    for family in families:
        cells = profiles(root, family, treatment, samples, seed, size)
        atomic_json(root/f'{family}-profiles.json', {v: {'profile': p.profile.model_dump(mode='json'),
            'source_hashes': p.source_hashes, 'contract_hash': p.contract_hash, 'software': software_identity()}
            for v, p in cells.items()})
        signature = None
        for variant, current in cells.items():
            pool = root / f'{family}-{variant}'
            print(f'Starting {family} {variant}', flush=True)
            summary, inspection, plan, prep, wall, sig, _ = run_pool(
                current, pool, root/'observations.jsonl', acknowledged_codes=ACKNOWLEDGED)
            record = {'family': family, 'variant': variant, 'accepted': summary['accepted_samples'],
                'inspection': inspection['status'], 'preparation_seconds': prep, 'generation_seconds': wall,
                'images_per_second': summary['accepted_samples']/wall, 'signature': sig,
                'execution': plan.as_dict(), 'pool': pool.name}
            records.append(record)
            atomic_json(root/'records.json', records)
            print(json.dumps(record), flush=True)
            if signature is None:
                signature = sig
            elif signature != sig:
                raise RuntimeError(f'{family}: geometry, masks or annotations differ')
    atomic_json(root/'summary.json', {'status': 'complete', 'records': records, 'limitations': [
        'Ordered single pass without separate warmups; throughput is exploratory.',
        'Synthetic scenes share an asset catalog; no real-image or detector benefit is established.']})


def run(root, families, treatment, samples, seed, size, policy_path):
    policy_bytes = policy_path.read_bytes()
    policy = Policy.model_validate_json(policy_bytes)
    memory = psutil.virtual_memory()
    guards = resolve_guards(policy.guards, memory.total, memory.available)
    root.mkdir(parents=True, exist_ok=False)
    (root/'policy.json').write_bytes(policy_bytes)
    shutil.copyfile(__file__, root/'driver-source.py')
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--output-dir', str(root),
        '--families', *families, '--treatment', treatment, '--samples', str(samples),
        '--seed', str(seed), '--size', str(size)]
    atomic_json(root/'invocation.json', {'command': command, 'policy_sha256': hashlib.sha256(policy_bytes).hexdigest(),
        'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'note': 'One worker and one native thread; ordered single-pass cells.'})
    atomic_json(root/'guard-basis.json', {'available_bytes': memory.available, 'total_bytes': memory.total,
        'swap_out_initial_bytes': psutil.swap_memory().sout, 'guards': guards,
        'timeout_seconds': policy.guards.timeout_seconds})
    outcome = monitor([command], root, 'study', policy.guards.timeout_seconds, guards)
    atomic_json(root/'result.json', outcome)
    if outcome['status'] != 'complete':
        raise RuntimeError(f"Study ended with {outcome['status']}: {outcome['reason']}; see {root}")
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--families', nargs='+', choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument('--treatment', choices=('coherent-candidate', 'coherent-refined', 'coherent-directional', 'coherent-varied', 'coherent-varied-manometro'), default='coherent-candidate')
    parser.add_argument('--samples', type=int, default=4)
    parser.add_argument('--seed', type=int, default=20261031)
    parser.add_argument('--size', type=int, default=640)
    parser.add_argument('--policy', type=Path, default=DEFAULT_POLICY)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (not 1 <= args.samples <= 100 or args.seed < 0 or not 64 <= args.size <= 1280
            or len(set(args.families)) != len(args.families)):
        parser.error('Require 1–100 samples, nonnegative seed, size 64–1280 and unique families')
    root = args.output_dir.resolve()
    if args.worker:
        worker(root, args.families, args.treatment, args.samples, args.seed, args.size)
    else:
        print(run(root, args.families, args.treatment, args.samples, args.seed, args.size, args.policy.resolve()))


if __name__ == '__main__':
    main()
