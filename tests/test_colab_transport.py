"""Contract checks for the portable transfer helper shared by legacy studies."""
import copy
import runpy
from pathlib import Path

import pytest


def test_transport_runs_standalone_and_rejects_invalid_manifests(tmp_path):
    # This exact helper is uploaded without the surrounding repository.
    portable = tmp_path / 'remote_helper.py'
    portable.write_bytes(Path('experiments/shared/colab_transport.py').read_bytes())
    helper = runpy.run_path(str(portable))
    payload = tmp_path / 'payload'
    payload.write_bytes(b'portable input' * 40)
    manifest = helper['split_bundle'](payload, tmp_path / 'parts', 100)
    for change in ('path', 'whole_hash', 'size'):
        broken = copy.deepcopy(manifest)
        if change == 'path':
            broken['chunks'][0]['name'] = '../payload'
        elif change == 'whole_hash':
            broken['sha256'] = '0' * 64
        else:
            broken['chunks'][0]['bytes'] += 1
        output = tmp_path / change
        with pytest.raises(ValueError):
            helper['assemble_bundle'](tmp_path / 'parts', output, broken)
        assert not output.exists()
        assert not output.with_suffix('.partial').exists()
    output = tmp_path / 'result'
    helper['assemble_bundle'](tmp_path / 'parts', output, manifest)
    assert output.read_bytes() == payload.read_bytes()
    with pytest.raises(FileExistsError):
        helper['assemble_bundle'](tmp_path / 'parts', output, manifest)
    assert output.read_bytes() == payload.read_bytes()


def test_cli_logs_redact_proxy_token_and_propagate_failure(monkeypatch, capsys):
    import subprocess
    helper = runpy.run_path('experiments/shared/colab_transport.py')
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 2,
            stdout='url?colab-runtime-proxy-token=private-token&x=1\n')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    with pytest.raises(RuntimeError, match='sessions exited 2'):
        helper['call']('/usr/bin/colab', 'sessions')
    assert seen == [['/usr/bin/colab', '--auth=oauth2', 'sessions']]
    output = capsys.readouterr().out
    assert 'private-token' not in output
    assert '[REDACTED]&x=1' in output
    assert helper['call']('/usr/bin/colab', 'sessions', check=False).returncode == 2
