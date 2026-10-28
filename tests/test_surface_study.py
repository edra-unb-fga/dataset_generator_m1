import json

import pytest

from dataset_generator_m1.surface_study import BudgetLedger, BudgetPolicy


POLICY = dict(total_seconds=120, prototype_seconds=24, final_reserve_seconds=30,
              cell_seconds=80, prototype_cell_seconds=12)


def test_one_budget_reserves_final_and_counts_failed_work(tmp_path):
    ledger = BudgetLedger(tmp_path, POLICY)
    assert ledger.reserve('main', 'development') == 80
    ledger.settle('main', [{'command_seconds': 66, 'status': 'failed'}], evidence_identity='source')
    assert ledger.allowance('development') == 24
    for name in ['prototype-a', 'prototype-b']:
        assert ledger.reserve(name, 'prototype') == 12
        ledger.settle(name, [{'command_seconds': 12, 'status': 'complete'}], evidence_identity=name)
    assert ledger.allowance('prototype') == 0
    assert ledger.allowance('development') == 0
    assert ledger.allowance('final') == 30
    assert BudgetLedger(tmp_path, POLICY).used() == 90


def test_interrupted_work_cannot_refund_itself_or_reuse_a_cell(tmp_path):
    ledger = BudgetLedger(tmp_path, POLICY)
    ledger.reserve('interrupted', 'prototype')
    recovered = BudgetLedger(tmp_path, POLICY)
    assert recovered.used('prototype') == 12
    with pytest.raises(ValueError, match='already reserved'):
        recovered.reserve('interrupted', 'prototype')
    with pytest.raises(ValueError, match='changed'):
        BudgetLedger(tmp_path, {**POLICY, 'total_seconds': 121})


def test_budget_rejects_invalid_evidence_and_detects_overrun(tmp_path):
    ledger = BudgetLedger(tmp_path, POLICY)
    ledger.reserve('probe', 'prototype')
    for value in [[], [{'command_seconds': float('nan')}], [{'command_seconds': -1}]]:
        with pytest.raises(ValueError, match='timing'):
            ledger.settle('probe', value, evidence_identity='source')
    with pytest.raises(RuntimeError, match='exceeded'):
        ledger.settle('probe', [{'command_seconds': 13, 'status': 'complete'}], evidence_identity='source')
    assert json.loads((tmp_path/'budget.json').read_text())['entries'][0]['charged_seconds'] == 13
    with pytest.raises(ValueError):
        BudgetPolicy(**{**POLICY, 'prototype_seconds': 100})


def test_invalid_prelaunch_inputs_do_not_spend_or_poison_cell_id(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from dataset_generator_m1 import surface_study as module
    matrix = {'budget': POLICY, 'phases': {'preview': {'track': 'development', 'config': {},
               'recipes': ['base']}}, 'recipes': {'base': {'treatment': {}}}}
    path = tmp_path/'matrix.json'
    path.write_text(json.dumps(matrix))
    monkeypatch.setattr(module, 'load_config', lambda _: SimpleNamespace(model_dump=lambda **_: {'study_seconds': 100}))
    def invalid_asset(*args):
        raise ValueError('Bad asset')
    monkeypatch.setattr(module, 'prepare', invalid_asset)
    root = tmp_path/'study'
    with pytest.raises(ValueError, match='Unknown'):
        module.run_cell(root, 'config', path, 'preview', 'reusable', 'blenderproc', 'blender', recipe_ids=['typo'])
    assert BudgetLedger(root, POLICY).used() == 0
    with pytest.raises(ValueError, match='Bad asset'):
        module.run_cell(root, 'config', path, 'preview', 'reusable', 'blenderproc', 'blender')
    assert BudgetLedger(root, POLICY).used() == 0
    assert not BudgetLedger(root, POLICY).value['entries']
