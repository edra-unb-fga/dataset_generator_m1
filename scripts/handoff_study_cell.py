#!/usr/bin/env python3
"""Package and retrieve finished study cells only between timed commands.

Examples:
  python scripts/handoff_study_cell.py package --root STUDY --cell core --archive core.tar.gz
  python scripts/handoff_study_cell.py import --archive core.tar.gz --output IMPORTS
  python scripts/handoff_study_cell.py colab --remote /content/core.tar.gz --output IMPORTS \\
      --cache DOWNLOADS --executable colab --session SESSION
The calling study controller must pause before package/download and resume only after
completion. Colab credentials and any CLI configuration remain external to this tool.
"""
import argparse
import json
import sys
from dataset_generator_m1.cell_handoff import package, import_archive, import_colab


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('package'); p.add_argument('--root', required=True); p.add_argument('--cell', required=True); p.add_argument('--archive', required=True)
    p = commands.add_parser('import'); p.add_argument('--archive', required=True); p.add_argument('--output', required=True)
    p = commands.add_parser('colab'); p.add_argument('--remote', required=True); p.add_argument('--output', required=True); p.add_argument('--cache', required=True); p.add_argument('--executable', required=True); p.add_argument('--session', required=True)
    args = parser.parse_args()
    if args.command == 'package': result = package(args.root, args.cell, args.archive)
    elif args.command == 'import': result = import_archive(args.archive, args.output)
    else: result = import_colab(args.remote, args.output, executable=args.executable, session=args.session, cache=args.cache)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({'status': 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                          'error': str(exc), 'retry': 'Retry the cell handoff at a between-cell barrier.'}), file=sys.stderr)
        sys.exit(1)
