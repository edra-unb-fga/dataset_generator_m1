#!/usr/bin/env python3
"""Read-only, bounded inventory of top-level experiment output entries."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def inventory(root: Path, max_entries: int = 100_000, max_depth: int = 12) -> list[dict]:
    if max_entries < 1 or max_depth < 0:
        raise ValueError("max_entries must be positive and max_depth nonnegative")
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"not a directory or is a symlink: {root}")
    results = []
    # Sorting top-level entries makes output stable; the per-run budget bounds traversal.
    with os.scandir(root) as entries:
        top = sorted(entries, key=lambda entry: entry.name)
    for entry in top:
        record = {"name": entry.name, "bytes": 0, "files": 0, "status": "unclassified",
                  "report": False, "evidence": False, "truncated": False, "errors": []}
        stack = [(entry.path, 0)]
        visited = 0
        while stack:
            path, depth = stack.pop()
            if visited >= max_entries:
                record["truncated"] = True
                break
            visited += 1
            try:
                if os.path.islink(path):
                    continue
                stat = os.stat(path, follow_symlinks=False)
                if os.path.isdir(path):
                    if depth >= max_depth:
                        record["truncated"] = True
                        continue
                    with os.scandir(path) as children:
                        # Stop collecting entries at the remaining budget, too.
                        for child in children:
                            if len(stack) + visited >= max_entries:
                                record["truncated"] = True
                                break
                            stack.append((child.path, depth + 1))
                elif os.path.isfile(path):
                    record["bytes"] += stat.st_size
                    record["files"] += 1
                    name = Path(path).name.lower()
                    if name.endswith('.html') or 'report' in name:
                        record["report"] = True
                    if name.endswith(('.json', '.jsonl', '.csv', '.png', '.jpg', '.jpeg', '.log')):
                        record["evidence"] = True
                    if name in ('progress.json', 'run.json', 'summary.json', 'study.json'):
                        record["status"] = "metadata present; inspect to determine outcome"
            except OSError as exc:
                record["errors"].append(f"{path}: {exc.strerror}")
        results.append(record)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?', default=Path('outputs/experiments'))
    parser.add_argument('--max-entries', type=int, default=100_000, help='maximum entries visited per top-level item')
    parser.add_argument('--max-depth', type=int, default=12, help='maximum traversal depth per item')
    parser.add_argument('--json', action='store_true', help='emit JSON')
    args = parser.parse_args()
    try:
        records = inventory(args.root, args.max_entries, args.max_depth)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print('NAME\tBYTES\tFILES\tSTATUS\tREPORT\tEVIDENCE\tTRUNCATED\tERRORS')
        for row in records:
            print(f"{row['name']}\t{row['bytes']}\t{row['files']}\t{row['status']}\t{row['report']}\t{row['evidence']}\t{row['truncated']}\t{len(row['errors'])}")


if __name__ == '__main__':
    main()
