"""Compatibility entry point for pinned material acquisition. See docs/MATERIALS.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dataset_generator_m1.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["materials", *sys.argv[1:]]))
