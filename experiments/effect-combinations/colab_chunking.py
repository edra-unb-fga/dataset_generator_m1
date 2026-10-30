"""Compatibility entry point for the shared, self-contained transfer helper."""
from pathlib import Path
import runpy

_helper = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'shared/colab_transport.py'))
MAX_CHUNK_BYTES = _helper['MAX_CHUNK_BYTES']
split_bundle = _helper['split_bundle']
assemble_bundle = _helper['assemble_bundle']
