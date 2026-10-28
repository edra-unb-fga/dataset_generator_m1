"""The Colab study controller must not persist proxy tokens from CLI errors."""
import subprocess
import sys
from pathlib import Path


def test_controller_redacts_proxy_token_in_cli_output(tmp_path):
    executable=tmp_path/'fake-colab'
    executable.write_text('#!/bin/sh\nif [ "$2" = new ]; then echo "request failed ?colab-runtime-proxy-token=SECRET123&x=y"; exit 1; fi\nif [ "$2" = stop ]; then exit 0; fi\nexit 1\n')
    executable.chmod(0o755)
    result=subprocess.run([sys.executable,'experiments/blenderproc/studies/l4-camera-completion/supervisor.py','--colab',str(executable),'--output',str(tmp_path/'out'),'--watchdog-seconds','1'],capture_output=True,text=True,check=True)
    assert 'SECRET123' not in result.stdout
    assert 'colab-runtime-proxy-token=[REDACTED]' in result.stdout
