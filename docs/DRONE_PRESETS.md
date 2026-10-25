# Drone scenario candidates

The four `drone-*-candidate` appearance bundles are experimental opt-ins for landing/landing-pad:
daylight, overcast, light haze, and motion/compression. All camera/lighting treatments affect the
composed frame, preserving geometry/alpha evidence. Existing current-fast, realistic-heavy, legacy,
RandomFog and stress choices remain available; the shipped default is unchanged.

Use the catalog command to read executable parameters and README guidance. No physical calibration
or detector-accuracy claim is implied by a scenario name.

```powershell
uv run python scripts/study_drone_presets.py --family landing-pad --output-dir outputs/experiments/pad-drone-review --warmups 2 --samples 20
```

Repeat for landing. Manometro is a two-baseline regression/control comparison rather than a drone
scenario. Each candidate has natural activation and a forced diagnostic treatment on paired scene
plans. Inspect natural activation counts and low-coverage warnings before interpreting mean costs.
The report preserves all source/geometry/mask/annotation invariants. Material comparisons intentionally
change content and must be studied separately from appearance-only pairs.

Review scale, perspective, symbol legibility, shared lighting, ground plausibility, blur/compression
severity and annotation validity. Use real reference images when available. Keep raw reports ignored;
promote compact conclusions, fingerprints, limitations and one selected contact sheet only.
