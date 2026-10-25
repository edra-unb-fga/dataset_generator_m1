"""Time real background recipes and non-overlapping synthesis operations.

This read-only study keeps QA enabled, uses one common first-source RNG stream per fixture, and
rotates recipe order. Different recipes deliberately change content and are not appearance pairs.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dataset_generator_m1 import backgrounds
from dataset_generator_m1.assets import build_asset_catalog
from dataset_generator_m1.augmentation_study import balanced_treatment_order
from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import execution_scope, plan_execution
from dataset_generator_m1.identities import software_identity
from dataset_generator_m1.scene import derive_seed


OPERATIONS = {
    "_load_rgb_float": "decode_to_float", "_resize_cover_crop": "resize_crop",
    "_palette_transfer": "palette_transfer", "_normalize_mask": "mask_preparation",
    "_multiband_blend": "multiband_blend", "_displace": "displacement",
    "_qa": "qa", "_perceptual_hash": "similarity_hash",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="examples/configs/landing-pad_minimal.yaml")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--size", type=int, default=1280, help="Output size; scene canvas follows canvas_scale")
    args = parser.parse_args()
    if args.samples < 1 or args.warmups < 0 or args.size < 1 or args.output_dir.exists():
        raise ValueError("Use positive samples/size, nonnegative warmups and a fresh output directory")
    resolved = load_profile(args.config)
    catalog = build_asset_catalog(resolved)
    synthesizer = backgrounds.BackgroundSynthesizer(catalog, resolved.recipes,
        resolved.profile.assets.backgrounds.group_weights, resolved.profile.assets.backgrounds.asset_weights)
    names = tuple(resolved.recipes.recipes)
    size = (round(args.size * resolved.profile.scene.canvas_scale),) * 2
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "gallery").mkdir()
    records = []
    measured = {}

    def wrapper(function, label):
        def timed(*values, **keywords):
            started = perf_counter_ns()
            try:
                return function(*values, **keywords)
            finally:
                measured[label] = measured.get(label, 0) + perf_counter_ns() - started
        return timed

    with execution_scope(plan_execution(resolved)), ExitStack() as patches:
        for function, label in OPERATIONS.items():
            patches.enter_context(patch.object(backgrounds, function, wrapper(getattr(backgrounds, function), label)))
        for fixture in range(args.warmups + args.samples):
            for recipe in balanced_treatment_order(names, fixture):
                measured.clear()
                started = perf_counter_ns()
                sample = synthesizer.synthesize(recipe, size, np.random.default_rng(
                    derive_seed(resolved.profile.run.seed, fixture, 0, "recipe-cost-pair")))
                duration = perf_counter_ns() - started
                if fixture < args.warmups:
                    continue
                operations = dict(measured)
                operations["other_synthesis"] = max(0, duration - sum(operations.values()))
                name = f"fixture-{fixture-args.warmups:03d}--{recipe}.jpg"
                record = {"fixture": fixture-args.warmups, "recipe": recipe, "canvas_size": size,
                          "duration_ns": duration, "operations_ns": operations,
                          "node_timings_ns": sample.node_timings_ns, "qa": sample.qa,
                          "warnings": sample.warnings, "sources": sample.source_assets,
                          "pixel_sha256": hashlib.sha256(sample.image.tobytes()).hexdigest(), "image": name}
                preview = Image.fromarray(sample.image)
                preview.thumbnail((900, 900))
                preview.save(args.output_dir / "gallery" / name, quality=90)
                records.append(record)
                with (args.output_dir / "measurements.jsonl").open("a") as handle:
                    handle.write(json.dumps(record) + "\n")
    summary = {"schema_version": 1, "status": "complete", "samples_per_recipe": args.samples,
               "warmups_per_recipe": args.warmups, "canvas_size": size, "software": software_identity(),
               "scope": "Production synthesis with QA intact; instrumented function wall times; no foreground rendering",
               "catalog_fingerprint": catalog.fingerprint, "recipes": {}}
    for recipe in names:
        rows = [r for r in records if r["recipe"] == recipe]
        summary["recipes"][recipe] = {
            "mean_seconds": float(np.mean([r["duration_ns"] for r in rows]) / 1e9),
            "p95_seconds": float(np.percentile([r["duration_ns"] for r in rows], 95) / 1e9),
            "mean_operations_seconds": {op: float(np.mean([r["operations_ns"].get(op, 0) for r in rows])/1e9)
                                        for op in [*OPERATIONS.values(), "other_synthesis"]}}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
