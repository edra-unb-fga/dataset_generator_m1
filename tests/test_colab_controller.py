"""The Colab study controller must not persist proxy tokens from CLI errors."""
import runpy
import subprocess
import sys


def test_controller_redacts_proxy_token_in_cli_output(tmp_path, monkeypatch, capsys):
    def fake_run(command, **kwargs):
        operation=command[2]
        if operation == 'new':
            return subprocess.CompletedProcess(command, 1, stdout='request failed ?colab-runtime-proxy-token=SECRET123&x=y')
        return subprocess.CompletedProcess(command, 0 if operation == 'stop' else 1, stdout='')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, 'argv', ['supervisor.py', '--colab', 'fake-colab',
                                     '--output', str(tmp_path/'out'), '--watchdog-seconds', '1'])
    runpy.run_path('experiments/blenderproc/studies/l4-camera-completion/supervisor.py', run_name='__main__')
    output=capsys.readouterr().out
    assert 'SECRET123' not in output
    assert 'colab-runtime-proxy-token=[REDACTED]' in output
