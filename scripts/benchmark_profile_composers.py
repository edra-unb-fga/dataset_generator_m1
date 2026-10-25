"""Compare appearance and explicit content-changing composer choices through production generation.

Each repetition rotates composer order. Each cell runs in a fresh process, including its own
separate warmup pool and preparation. Raw bundles stay ignored; existing destinations are refused.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

import psutil
import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("examples/configs/landing-pad_minimal.yaml"))
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if min(args.samples, args.repeats) < 1 or args.warmups < 0 or args.output_dir.exists():
        raise ValueError("Use positive samples/repeats, nonnegative warmups and a fresh destination")
    base = yaml.safe_load(args.config.read_text())
    choices = {name: (name, "standard") for name in
               ("current-fast", "realistic-heavy", "camera-minimal", "camera-balanced")}
    choices["direct-camera"] = ("camera-minimal", "direct-dominant")
    args.output_dir.mkdir(parents=True)
    composers = {}
    for name, (appearance, mixing) in choices.items():
        composer = {**base, "appearance": {"preset": "builtin:appearance/" + appearance},
                    "background_mixing": "builtin:background_mixing/" + mixing}
        path = args.output_dir / (name + ".yaml")
        path.write_text(yaml.safe_dump(composer, sort_keys=False))
        composers[name] = path
    records = []
    names = list(choices)
    for repeat in range(args.repeats):
        for name in names[repeat % len(names):] + names[:repeat % len(names)]:
            destination = args.output_dir / f"{repeat:02d}-{name}"
            command = [sys.executable, "-m", "dataset_generator_m1", "benchmark", "--production",
                       "--config", str(composers[name]), "--samples", str(args.samples),
                       "--warmup", str(args.warmups), "--repeats", "1", "--output-dir", str(destination),
                       "--output-format", "json"]
            (args.output_dir / "progress.json").write_text(json.dumps({"repeat": repeat, "composer": name, "completed": len(records)}))
            started = monotonic()
            psutil.cpu_percent(None)
            with (args.output_dir / f"{repeat:02d}-{name}.log").open("w") as log, \
                 (args.output_dir / f"{repeat:02d}-{name}-system.jsonl").open("w") as system:
                process = subprocess.Popen(command, env={**os.environ, "PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1"},
                                           stdout=log, stderr=subprocess.STDOUT)
                while True:
                    memory, swap = psutil.virtual_memory(), psutil.swap_memory()
                    system.write(json.dumps({"elapsed": monotonic()-started, "available_memory_bytes": memory.available,
                        "swap_used_bytes": swap.used, "swap_in_bytes": swap.sin, "swap_out_bytes": swap.sout,
                        "cpu_percent": psutil.cpu_percent(None), "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None}) + "\n")
                    system.flush()
                    try:
                        code = process.wait(timeout=2)
                        break
                    except subprocess.TimeoutExpired:
                        pass
            if code:
                raise RuntimeError(f"{name} failed; inspect its raw log")
            result = json.loads((destination / "benchmark.json").read_text())
            row = result["records"][0]
            if result["status"] != "complete" or row["accepted"] != args.samples:
                raise RuntimeError(f"{name} did not complete valid accepted-output generation")
            records.append({**row, "composer": name, "repeat": repeat, "command_seconds": monotonic()-started})
            (args.output_dir / "records.json").write_text(json.dumps(records, indent=2))
            print(f"{repeat+1}/{args.repeats} {name}: {row['throughput']:.3f} accepted images/s", flush=True)
    for name in names:
        if len({r["content_signature"] for r in records if r["composer"] == name}) != 1:
            raise RuntimeError(f"{name} content changed between repetitions")
    standard = [r for r in records if r["composer"] != "direct-camera"]
    if len({r["content_signature"] for r in standard}) != 1:
        raise RuntimeError("Appearance-only composers changed geometry/annotation/mask evidence")
    summary = {"schema_version": 1, "status": "complete", "samples": args.samples, "repeats": args.repeats,
               "warmups": args.warmups, "low_sample": args.samples < 20 or args.repeats < 3,
               "scope": "Environment-local accepted-output generation; direct-camera deliberately changes background content",
               "appearance_only_signatures_equal": True, "records": records}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (args.output_dir / "progress.json").write_text(json.dumps({"status": "complete", "completed": len(records)}))


if __name__ == "__main__":
    main()
