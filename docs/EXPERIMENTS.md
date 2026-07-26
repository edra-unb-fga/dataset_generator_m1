# Controlled Experiments

Experiments are read-only analyses of the production pipeline. Their job is to isolate a decision,
preserve paired inputs, and make evidence inspectable—not to create a second renderer.

## Augmentation attribution

Run the default paired study:

```powershell
uv run python -m dataset_generator_m1 experiment augmentations `
  --config examples/configs/landing_minimal.yaml `
  --output-dir outputs/experiments/landing-heavy
```

Use `--warmups`, `--samples`, and `--include-stress` deliberately. A custom `--matrix` is strict and
may change only the three appearance stages. Geometry, source assets, recipes, sampling, and output
dimensions remain paired.

The default treatments are `no-appearance`, `current`, `legacy-heavy-compatible`, three isolated
realistic-heavy stages, and `realistic-heavy-combined`. The legacy treatment is diagnostic and maps
unsupported `AtmosphericFog` to `RandomFog`; this approximation is disclosed in every report.
`all-effects-stress` is benchmark-only. Normal generation never selects either profile implicitly.
Visual review rejected `RandomFog` for the realistic preset because even low-density settings softened
the complete frame and obscured labels. Realistic weather uses light drizzle instead; fog remains only
in the disclosed legacy-compatible and stress treatments.

The reviewed realistic-heavy treatment is an explicit opt-in:

```powershell
uv run python -m dataset_generator_m1 generate `
  --config examples/configs/landing_minimal.yaml `
  --appearance-preset realistic-heavy `
  --num-images 20 `
  --output-dir outputs/landing-realistic-heavy
```

## Interpretation rules

- Causal performance conclusions apply only to paired treatments in the same environment.
- Use render-only cost to identify appearance work and modeled production cost to include the shared
  synthesis, encode, and write work a normal sample would incur.
- Inclusive scene-render duration is not the sum of nested spans. Effect traces are exclusive calls.
- Compare per-call, per-object, and per-megapixel values before generalizing.
- Fewer than 20 measured fixtures produces a low-sample warning.
- Do not establish cross-machine thresholds until hardware classes have reviewed baselines.

Raw bundles under `outputs/experiments/` are ignored. A reviewed study may promote only its definition,
compact conclusions, environment/profile fingerprints, and a small contact sheet into `docs/experiments/`.

## Report layout verdict

The retained `codex/prototype-augmentation-report` branch compares three image-first layouts. The
synchronized contact-sheet design is the production default because it keeps the causal pair visible.
Slow-sample navigation, stage tabs, and difference views remain secondary investigation tools.
