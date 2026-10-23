"""Reanalyse existing measurements (never rerender) and retain compact reviewed evidence."""
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dataset_generator_m1.augmentation_study import _summarize, _render_report, validate_study_artifacts


def main():
    destination = Path("docs/experiments/drone-screen-v1")
    destination.mkdir(parents=True, exist_ok=True)
    compact = {"scope": "scenario-based initial screen; not physical calibration or training evidence", "families": {}}
    for family, directory in (("landing-pad", "pad"), ("landing", "landing"), ("manometro", "manometro")):
        root = Path(f"outputs/experiments/{directory}-drone-v1")
        records = [json.loads(line) for line in (root / "measurements.jsonl").read_text().splitlines() if line.strip()]
        summary = json.loads((root / "summary.json").read_text())
        summary["analysis"] = _summarize(records, summary["study"]["samples"])
        (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        _render_report(summary, records, root)
        validate_study_artifacts(root)
        compact["families"][family] = {
            "environment": summary["environment"], "study": summary["study"],
            "measurements_sha256": hashlib.sha256((root / "measurements.jsonl").read_bytes()).hexdigest(),
            "analysis": summary["analysis"],
        }
        # Keep reviewed conclusions compact; the ignored raw bundle retains full traces.
        import copy
        compact["families"][family]["analysis"] = copy.deepcopy(summary["analysis"])
        for ranking in compact["families"][family]["analysis"]["slow_samples"].values():
            for row in ranking:
                row["rejection_count"] = len(row.pop("rejections"))
                for effect in row["active_effects"]:
                    effect.pop("params", None)
        # One synchronized row, baseline and four naturally sampled scenarios.
        names = ["current-fast", "realistic-heavy"] + ([] if family == "manometro" else [
            "drone-daylight-candidate", "drone-overcast-candidate", "drone-haze-candidate", "drone-motion-candidate"])
        from PIL import ImageDraw
        sheet = Image.new("RGB", (260 * len(names), 300), "#111820")
        draw = ImageDraw.Draw(sheet)
        for index, name in enumerate(names):
            record = next(item for item in records if item["fixture_index"] == 0 and item["treatment"] == name)
            with Image.open(root / "report/gallery" / record["image"]) as image:
                image.thumbnail((250, 250))
                sheet.paste(image.convert("RGB"), (index * 260 + 5, 5))
            draw.text((index * 260 + 5, 265), name.replace("-candidate", ""), fill="white")
        sheet.save(destination / f"{family}.jpg", quality=85)
    (destination / "summary.json").write_text(json.dumps(compact, indent=2), encoding="utf-8")
    print(json.dumps({family: {name: round(value["render_mean_ns"] / 1e9, 3) for name, value in data["analysis"]["treatments"].items()}
                      for family, data in compact["families"].items()}, indent=2))


if __name__ == "__main__":
    main()
