"""Shared, restart-safe accounting for optional surface studies and isolated prototypes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .blender_pilot import atomic_json, digest, load_config, prepare, run_study, export_study, report
from .ownership import CoordinatorLease


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    total_seconds: float = Field(gt=0)
    prototype_seconds: float = Field(ge=0)
    final_reserve_seconds: float = Field(gt=0)
    cell_seconds: float = Field(gt=0)
    prototype_cell_seconds: float = Field(gt=0)

    @model_validator(mode='after')
    def allocation(self):
        if self.prototype_seconds + self.final_reserve_seconds > self.total_seconds:
            raise ValueError('Prototype allocation and final reserve exceed total budget')
        return self


class BudgetLedger:
    """Caller holds one CoordinatorLease while reserving, executing and settling work.

    An interrupted reservation remains charged at its full allowance. It can be reconciled
    only from the recorded child run evidence, never automatically refunded on restart.
    """
    def __init__(self, root, policy):
        self.root = Path(root)
        self.policy = BudgetPolicy.model_validate(policy)
        self.path = self.root / 'budget.json'
        if self.path.exists():
            self.value = json.loads(self.path.read_text())
            if self.value['policy'] != self.policy.model_dump(mode='json'):
                raise ValueError('Study budget policy changed')
        else:
            self.value = {'schema_version': 1, 'policy': self.policy.model_dump(mode='json'), 'entries': []}

    def used(self, track=None):
        return sum(e['charged_seconds'] for e in self.value['entries'] if track is None or e['track'] == track)

    def allowance(self, track):
        if track not in ('development', 'prototype', 'final'):
            raise ValueError('Unknown budget track')
        remaining = max(0., self.policy.total_seconds - self.used())
        if track != 'final':
            remaining = max(0., remaining - self.policy.final_reserve_seconds)
        limit = self.policy.cell_seconds
        if track == 'prototype':
            remaining = min(remaining, max(0., self.policy.prototype_seconds - self.used('prototype')))
            limit = self.policy.prototype_cell_seconds
        return min(remaining, limit)

    def reserve(self, name, track):
        if any(e['name'] == name for e in self.value['entries']):
            raise ValueError('Cell already reserved; use a new ID for retries')
        seconds = self.allowance(track)
        if seconds <= 0:
            raise ValueError('Budget or final reserve prevents further work')
        entry = {'name': name, 'track': track, 'allowance_seconds': seconds,
                 'charged_seconds': seconds, 'status': 'reserved'}
        self.value['entries'].append(entry)
        atomic_json(self.path, self.value)
        return seconds

    def settle(self, name, runs, *, evidence_identity):
        entry = next(e for e in self.value['entries'] if e['name'] == name)
        if entry['status'] != 'reserved':
            raise ValueError('Cell already settled')
        if not runs or any(not isinstance(r.get('command_seconds'), (int, float)) or
                           not 0 <= r['command_seconds'] < float('inf') for r in runs):
            raise ValueError('Complete finite command timing evidence required')
        seconds = sum(r['command_seconds'] for r in runs)
        entry.update(charged_seconds=seconds, status='settled', evidence_identity=evidence_identity,
                     outcome=runs[-1]['status'])
        atomic_json(self.path, self.value)
        if seconds > entry['allowance_seconds']:
            raise RuntimeError('Cell exceeded its reserved budget; no further work is authorized')


def run_cell(root, base_config, matrix_path, phase, cell_id, blenderproc, install, *, recipe_ids=None):
    """Prepare a fresh bounded cell from saved recipes; retain rejected/partial evidence."""
    root = Path(root).resolve()
    matrix_path = Path(matrix_path).resolve()
    matrix = json.loads(matrix_path.read_text())
    policy = BudgetPolicy.model_validate(matrix['budget'])
    if phase not in matrix['phases'] or not cell_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in cell_id):
        raise ValueError('Unknown phase or invalid cell ID')
    with CoordinatorLease(root):
        design = {'matrix': matrix, 'matrix_sha256': hashlib.sha256(matrix_path.read_bytes()).hexdigest()}
        if (root/'design.json').exists() and json.loads((root/'design.json').read_text()) != design:
            raise ValueError('Frozen study matrix changed; prepare a new study root')
        atomic_json(root/'design.json', design)
        ledger = BudgetLedger(root, policy)
        setting = matrix['phases'][phase]
        allowance = ledger.reserve(cell_id, setting['track'])
        config = load_config(base_config).model_dump(mode='json')
        config.update(setting['config'])
        ids = recipe_ids if recipe_ids is not None else setting['recipes']
        if not ids or len(ids) != len(set(ids)) or set(ids) - set(matrix['recipes']):
            raise ValueError('Unknown, duplicate or empty recipe selection')
        config['treatments'] = [dict(matrix['recipes'][name]['treatment'], id=name) for name in ids]
        # The phase decides quality jobs explicitly; no fallback quality work is hidden.
        config['quality_treatments'] = [name for name in setting.get('quality_recipes', []) if name in ids]
        config['study_seconds'] = min(allowance, config['study_seconds'])
        cell = root/'cells'/cell_id
        cell.parent.mkdir(parents=True, exist_ok=True)
        configuration = root/'configs'/(cell_id+'.json')
        atomic_json(configuration, config)
        study = prepare(configuration, cell)
        atomic_json(cell/'surface-origin.json', {'phase': phase, 'cell_id': cell_id,
                    'matrix_sha256': design['matrix_sha256'], 'track': setting['track'],
                    'recipes': {name: matrix['recipes'][name] for name in ids}})
        try:
            outcome = run_study(cell, blenderproc, install)
        finally:
            if (cell/'runs.json').exists():
                ledger.settle(cell_id, json.loads((cell/'runs.json').read_text()), evidence_identity=study['identity'])
        if outcome['status'] == 'complete':
            export_study(cell)
            report(cell)
        return {'cell': str(cell), 'identity': study['identity'], 'outcome': outcome,
                'budget_used_seconds': ledger.used(), 'total_seconds': policy.total_seconds}
