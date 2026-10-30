import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import guarded_foreground_context as guarded


def test_adaptive_guards_reserve_headroom():
    settings = guarded.Policy.model_validate_json(guarded.DEFAULT_POLICY.read_bytes()).guards
    guards = guarded.resolve_guards(settings, 16 * 2**30, 8 * 2**30)
    assert guards == {'min_available_gib': 2, 'rss_limit_gib': 4, 'max_swap_out_mib': 16}
    with pytest.raises(ValueError, match='Insufficient'):
        guarded.resolve_guards(settings, 16 * 2**30, 2 * 2**30)


def test_run_records_policy_invocation_and_guards_without_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(guarded.psutil, 'virtual_memory', lambda: SimpleNamespace(total=16*2**30, available=8*2**30))
    monkeypatch.setattr(guarded.psutil, 'swap_memory', lambda: SimpleNamespace(sout=42))
    observed = {}
    def fake_monitor(commands, root, name, seconds, guards):
        observed.update(command=commands[0], seconds=seconds, guards=guards)
        return {'status': 'complete', 'reason': None, 'returncodes': [0]}
    monkeypatch.setattr(guarded, 'monitor', fake_monitor)
    root = tmp_path/'study'
    result = guarded.run('examples/configs/landing-pad_minimal.yaml', root, 'development', 20)
    assert result == root
    assert json.loads((root/'result.json').read_text())['status'] == 'complete'
    assert json.loads((root/'execution.json').read_text())['workers'] == 2
    assert json.loads((root/'guard-basis.json').read_text())['swap_out_initial_bytes'] == 42
    assert observed['guards']['max_swap_out_mib'] == 16
    assert observed['seconds'] == 1800
    assert '--execution-policy' in observed['command'] and '--matrix' in observed['command']
    with pytest.raises(FileExistsError):
        guarded.run('examples/configs/landing-pad_minimal.yaml', root, 'development', 20)


def test_guard_abort_is_durable_and_never_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(guarded.psutil, 'virtual_memory', lambda: SimpleNamespace(total=16*2**30, available=8*2**30))
    monkeypatch.setattr(guarded.psutil, 'swap_memory', lambda: SimpleNamespace(sout=0))
    calls=[]
    def fail(*args):
        calls.append(args)
        return {'status': 'guard-aborted', 'reason': 'host-swap-out', 'returncodes': [-15]}
    monkeypatch.setattr(guarded, 'monitor', fail)
    root = tmp_path/'study'
    with pytest.raises(RuntimeError, match='guard-aborted'):
        guarded.run('examples/configs/landing-pad_minimal.yaml', root, 'reserved', 12)
    assert len(calls) == 1
    assert json.loads((root/'result.json').read_text())['reason'] == 'host-swap-out'
