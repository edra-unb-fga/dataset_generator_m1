"""Compare actual appearance bundles on paired production-rendered scenes.

Run from the repository root. Raw compositors, matrices, measurements and galleries stay in the
requested ignored output directory. Forced treatments diagnose coverage, not ordinary frequency.
"""
import argparse
import json
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dataset_generator_m1.augmentation_study import (
    AugmentationStudyRequest, run_augmentation_study, validate_study_artifacts,
)
from dataset_generator_m1.config import load_appearance_profile, load_profile
from dataset_generator_m1.execution import execution_scope, plan_execution


BASELINES = ("no-appearance", "current-fast", "realistic-heavy", "legacy-heavy-compatible")
DRONE = ("drone-daylight-candidate", "drone-overcast-candidate", "drone-motion-candidate", "drone-haze-candidate")
CAMERA = ("camera-minimal", "camera-balanced")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["landing", "landing-pad", "manometro"], required=True)
    parser.add_argument("--mode", choices=["natural", "forced", "effects", "stress"], default="natural")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--size", type=int, default=1280)
    parser.add_argument("--native-threads", type=int)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Use a fresh output directory")
    source = Path("examples/configs") / f"{args.family}_minimal.yaml"
    composer = yaml.safe_load(source.read_text())
    composer["inline"] = {"output": {"image_size": [args.size, args.size]}}
    if args.native_threads is not None:
        composer["inline"]["execution"] = {"native_threads": args.native_threads}
    # Resolve every appearance before writing any evidence.
    names = (*BASELINES, *(DRONE if args.family != "manometro" else ()), *CAMERA)
    definitions = {name: load_appearance_profile("builtin:appearance/" + name, source).model_dump(mode="json")
                   for name in names}
    if args.mode == "stress":
        definitions = {name: load_appearance_profile("builtin:appearance/" + name, source).model_dump(mode="json")
                       for name in ("no-appearance", "current-fast", "realistic-heavy", "random-fog-heavy", "all-effects-stress")}
    elif args.mode == "natural":
        if args.family == "landing-pad":
            for stage in ("background", "foreground", "final"):
                definitions["heavy-" + stage] = {
                    key: definitions["realistic-heavy"][key] if key == stage else []
                    for key in ("background", "foreground", "final")}
    elif args.mode == "forced":
        definitions = {name + ("-forced" if name != "no-appearance" else ""): {
            stage: [{**effect, "probability": 1.0} for effect in effects]
            for stage, effects in appearance.items()}
            for name, appearance in definitions.items() if name != "legacy-heavy-compatible"}
    else:
        heavy = definitions["realistic-heavy"]
        definitions = {"no-appearance": definitions["no-appearance"]}
        for stage, effects in heavy.items():
            for effect in effects:
                definitions[effect["id"]] = {key: [{**effect, "probability": 1.0}] if key == stage else []
                                             for key in ("background", "foreground", "final")}
        # Fog is a selectable capability, distinct from ordinary heavy appearance.
        for mode in ("linear", "diagonal", "radial"):
            definitions["native-fog-" + mode] = {"background": [], "foreground": [], "final": [
                {"id": "diagnostic-native-fog", "type": "AtmosphericFog", "probability": 1.0,
                 "params": {"density_range": [0.15, 0.25], "depth_mode": mode, "fog_color": [190, 195, 200]}}]}
        fog = load_appearance_profile("builtin:appearance/random-fog-heavy", source).model_dump(mode="json")
        definitions["random-fog-heavy-forced"] = {
            stage: [{**effect, "probability": 1.0} for effect in effects] for stage, effects in fog.items()}
    args.output_dir.mkdir(parents=True)
    config = args.output_dir / "composer.yaml"
    matrix = args.output_dir / "matrix.yaml"
    config.write_text(yaml.safe_dump(composer, sort_keys=False))
    matrix.write_text(yaml.safe_dump({"schema_version": 1, "treatments": definitions}, sort_keys=False))
    resolved = load_profile(config)
    plan = plan_execution(resolved)
    (args.output_dir / "execution.json").write_text(json.dumps(plan.as_dict(), indent=2))
    with execution_scope(plan):
        result = run_augmentation_study(AugmentationStudyRequest(
            config, args.output_dir, matrix=matrix, warmups=args.warmups, samples=args.samples))
    validation = validate_study_artifacts(args.output_dir)
    print(json.dumps({"family": args.family, "mode": args.mode, "samples": args.samples,
        "validation": validation, "treatments": {name: {
            "render_seconds": row["render_mean_ns"] / 1e9,
            "modeled_seconds": row["modeled_mean_ns"] / 1e9}
            for name, row in result["analysis"]["treatments"].items()}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
