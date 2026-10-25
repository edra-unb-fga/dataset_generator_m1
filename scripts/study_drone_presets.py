"""Paired appearance studies with natural and forced effect coverage, using production rendering."""
import argparse
import json
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dataset_generator_m1.augmentation_study import AugmentationStudyRequest, run_augmentation_study, validate_study_artifacts
from dataset_generator_m1.config import load_appearance_profile


IDS = ("current-fast", "realistic-heavy", "drone-daylight-candidate", "drone-overcast-candidate", "drone-haze-candidate", "drone-motion-candidate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["landing", "landing-pad", "manometro"], required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    args = parser.parse_args()
    config = Path("examples/configs") / f"{args.family}_minimal.yaml"
    ids = IDS[:2] if args.family == "manometro" else IDS
    # The matrix is an immutable snapshot of resolved profiles, retained with the raw study.
    definitions = {}
    for name in ids:
        appearance = load_appearance_profile("builtin:appearance/" + name, config).model_dump(mode="json")
        definitions[name] = appearance
        if name.endswith("candidate"):
            forced = {stage: [{**effect, "probability": 1.0} for effect in effects] for stage, effects in appearance.items()}
            definitions[name + "-forced"] = forced
    matrix = args.output_dir.with_name(args.output_dir.name + "-matrix.yaml")
    matrix.parent.mkdir(parents=True, exist_ok=True)
    if matrix.exists() or args.output_dir.exists():
        raise ValueError("Use a new study destination")
    matrix.write_text(yaml.safe_dump({"schema_version": 1, "treatments": definitions}, sort_keys=False), encoding="utf-8")
    result = run_augmentation_study(AugmentationStudyRequest(config, args.output_dir, matrix=matrix, warmups=args.warmups, samples=args.samples))
    validate_study_artifacts(args.output_dir)
    print(json.dumps({"status": result["status"], "family": args.family, "output": str(args.output_dir),
                      "mean_render_seconds": {name: value["render_mean_ns"] / 1e9 for name, value in result["analysis"]["treatments"].items()},
                      "warning_count": len(result["analysis"]["warnings"])}))


if __name__ == "__main__":
    main()
