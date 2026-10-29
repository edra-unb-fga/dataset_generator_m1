"""Run one paired 2D study under measured host-memory, swap-out and time guards.

A fresh output directory captures the exact policy, measured guard basis, subprocess
log, resource observations and completed/aborted result. Runs never resume or retry
with weaker limits automatically. Reserve selection and worker count are policy data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import signal
import sys

import psutil
from pydantic import BaseModel, ConfigDict, Field

from dataset_generator_m1.blender_runner import monitor
from dataset_generator_m1.models import ExecutionConfig
from study_foreground_context import DEFAULT_MATRIX
from study_surface_2d import atomic_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / 'experiments/foreground-context/local-cpu-policy.json'


class GuardSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    host_available_fraction_for_rss: float = Field(gt=0, lt=1)
    host_total_fraction_reserved: float = Field(gt=0, lt=1)
    host_minimum_reserve_gib: float = Field(gt=0)
    max_swap_out_mib: float = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


class Policy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    schema_version: int = Field(ge=1, le=1)
    execution: ExecutionConfig
    guards: GuardSettings


def resolve_guards(settings, total, available):
    if not 0 < available <= total:
        raise ValueError('Invalid host memory measurements')
    reserve = max(settings.host_minimum_reserve_gib, total / 2**30 * settings.host_total_fraction_reserved)
    rss = min(available / 2**30 * settings.host_available_fraction_for_rss, available / 2**30 - reserve)
    if rss <= 0:
        raise ValueError('Insufficient available memory for the requested reserve')
    return {'min_available_gib': reserve, 'rss_limit_gib': rss, 'max_swap_out_mib': settings.max_swap_out_mib}


def run(config, output_dir, phase, samples, policy_path=DEFAULT_POLICY, matrix_path=DEFAULT_MATRIX):
    policy_path, matrix_path, config = map(lambda p: Path(p).resolve(), (policy_path, matrix_path, config))
    policy_bytes = policy_path.read_bytes()
    policy = Policy.model_validate_json(policy_bytes)
    if phase not in ('development', 'reserved') or not 1 <= samples <= 100:
        raise ValueError('Invalid phase or sample count')
    if not config.is_file() or not matrix_path.is_file():
        raise ValueError('Configuration and matrix must exist')
    memory = psutil.virtual_memory()
    guards = resolve_guards(policy.guards, memory.total, memory.available)
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root/'policy.json').write_bytes(policy_bytes)
    shutil.copyfile(matrix_path, root/'matrix.json')
    shutil.copyfile(__file__, root/'guard-driver-source.py')
    atomic_json(root/'execution.json', policy.execution.model_dump(mode='json'))
    atomic_json(root/'guard-basis.json', {'total_bytes': memory.total, 'available_bytes': memory.available,
        'swap_out_initial_bytes': psutil.swap_memory().sout, 'guards': guards,
        'timeout_seconds': policy.guards.timeout_seconds})
    command = [sys.executable, str(ROOT/'scripts/study_foreground_context.py'), '--config', str(config),
        '--output-dir', str(root/'study'), '--phase', phase, '--samples', str(samples),
        '--matrix', str(root/'matrix.json'), '--execution-policy', str(root/'execution.json')]
    atomic_json(root/'invocation.json', {'command': command, 'phase': phase, 'samples': samples})
    atomic_json(root/'result.json', {'status': 'running'})
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt('Supervisor requested shutdown')
    previous_handler = signal.signal(signal.SIGTERM, interrupted)
    try:
        outcome = monitor([command], root, 'study', policy.guards.timeout_seconds, guards)
    except BaseException as exc:
        atomic_json(root/'result.json', {'status': 'monitor-interrupted', 'reason': type(exc).__name__})
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    atomic_json(root/'result.json', outcome)
    if outcome['status'] != 'complete':
        raise RuntimeError(f"Study ended with {outcome['status']}: {outcome['reason']}; see {root}")
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--phase', choices=('development', 'reserved'), required=True)
    parser.add_argument('--samples', type=int, required=True)
    parser.add_argument('--policy', default=DEFAULT_POLICY)
    parser.add_argument('--matrix', default=DEFAULT_MATRIX)
    args = parser.parse_args()
    print(run(args.config, args.output_dir, args.phase, args.samples, args.policy, args.matrix))


if __name__ == '__main__':
    main()
