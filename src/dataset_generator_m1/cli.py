from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import load_config
from .generator import DatasetGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dataset_generator_m1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a synthetic YOLO dataset")
    generate.add_argument("--config", type=str, default=None, help="Path to YAML config")
    generate.add_argument("--dataset-type", choices=["manometro", "landing"], default=None)
    generate.add_argument("--num-images", type=int, default=None)
    generate.add_argument("--output-dir", type=str, default=None)
    generate.add_argument("--debug", type=int, default=None)
    generate.add_argument("--debug-dir", type=str, default=None)
    generate.add_argument("--backgrounds-dir", type=str, default=None)
    generate.add_argument("--print-config", action="store_true", help="Print the resolved config before generating")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        return generate_command(args)
    return 1


def generate_command(args: argparse.Namespace) -> int:
    overrides: dict[str, Any] = {
        "dataset_type": args.dataset_type,
        "num_images": args.num_images,
        "output_dir": args.output_dir,
        "debug": args.debug,
        "debug_dir": args.debug_dir,
        "backgrounds_dir": args.backgrounds_dir,
    }
    config = load_config(args.config, overrides)
    if args.print_config:
        print(json.dumps(config.data, indent=2))
    generator = DatasetGenerator(config)
    manifest = generator.generate()
    output_dir = Path(config.data["output_dir"])
    print(f"Generated {len(manifest['samples'])} images in {output_dir}")
    return 0

