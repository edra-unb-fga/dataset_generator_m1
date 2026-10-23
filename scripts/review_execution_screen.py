"""Retain a small sanitized summary from the ignored production benchmark bundle."""
import hashlib
import json
from pathlib import Path
from statistics import median


root = Path("outputs/experiments/execution-screen-v1")
raw = json.loads((root / "benchmark.json").read_text())
result = {key: raw[key] for key in ("schema_version", "status", "scope", "software", "samples", "repeats", "warmup_samples_per_variant", "low_sample")}
result["raw_sha256"] = hashlib.sha256((root / "benchmark.json").read_bytes()).hexdigest()
result["provenance"] = {"base_commit": "9d34516", "working_tree": True, "limitation": "initial local screen before execution delivery commit; no hardware-class promotion"}
result["source_hashes"] = {name: hashlib.sha256((Path("src/dataset_generator_m1") / name).read_bytes()).hexdigest()
                           for name in ("execution.py", "decoded_cache.py", "imaging.py", "generator.py", "backgrounds.py", "execution_benchmark.py")}
result["variants"] = {}
for name in sorted({row["variant"] for row in raw["records"]}):
    rows = [row for row in raw["records"] if row["variant"] == name]
    result["variants"][name] = {
        "requested": rows[0]["execution"]["requested"],
        "active_seconds": [round(row["active_seconds"], 4) for row in rows],
        "wall_seconds": [round(row["wall_seconds"], 4) for row in rows],
        "median_throughput": median(row["throughput"] for row in rows),
        "accepted": [row["accepted"] for row in rows], "attempts": [row["attempts"] for row in rows],
        "content_signature": rows[0]["content_signature"],
        "peak_rss_bytes": [row["resource_peaks"].get("rss_bytes") for row in rows],
        "stage_total_ns": [{stage: value["total_ns"] for stage, value in row["stage_work"].items()} for row in rows],
    }
destination = Path("docs/experiments/execution-screen-v1")
destination.mkdir(parents=True, exist_ok=True)
(destination / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({name: {"active_seconds": value["active_seconds"], "median_throughput": round(value["median_throughput"], 3)}
                  for name, value in result["variants"].items()}, indent=2))
