"""Run saved optional surface-study cells under one shared render budget."""
import argparse
import json
from pathlib import Path

from dataset_generator_m1.surface_study import BudgetLedger, run_cell
from dataset_generator_m1.ownership import CoordinatorLease


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--config', required=True)
    run.add_argument('--matrix', required=True)
    run.add_argument('--output-dir', required=True)
    run.add_argument('--phase', required=True)
    run.add_argument('--cell-id', required=True)
    run.add_argument('--recipes', nargs='+')
    run.add_argument('--blenderproc', required=True)
    run.add_argument('--blender-install-path', required=True)
    budget = sub.add_parser('budget')
    budget.add_argument('--matrix', required=True)
    budget.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    if args.command == 'run':
        result = run_cell(args.output_dir, args.config, args.matrix, args.phase, args.cell_id,
                          args.blenderproc, args.blender_install_path, recipe_ids=args.recipes)
    else:
        matrix = json.loads(Path(args.matrix).read_text())
        with CoordinatorLease(args.output_dir):
            ledger = BudgetLedger(args.output_dir, matrix['budget'])
            result = {'used_seconds': ledger.used(), 'prototype_used_seconds': ledger.used('prototype'),
                      'allowances': {name: ledger.allowance(name) for name in ['development', 'prototype', 'final']}}
    print(json.dumps(result, indent=2))
    if args.command == 'run' and result['outcome']['status'] != 'complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
