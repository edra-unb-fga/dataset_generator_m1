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

That paragraph describes the historical default study, not the current effect catalog. The reviewed
[native fog comparison](experiments/native-fog-v1/README.md) keeps all three depth-dependent
`AtmosphericFog` modes and patch-based `RandomFog` available as distinct effects. It supplies paired
timing evidence for preflight warnings while leaving the earlier approximation record unchanged.

The reviewed realistic-heavy treatment is now the shipped composer default:

```powershell
uv run python -m dataset_generator_m1 generate `
  --config examples/configs/landing_minimal.yaml `
  --num-images 20 `
  --output-dir outputs/landing-realistic-heavy
```

The report's `current` treatment retains its historical meaning and resolves
`builtin:appearance/current-fast` explicitly.

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

The reviewed landing/manometro conclusion, compact measurements, environment fingerprints, and selected
visual evidence are stored in [`docs/experiments/augmentation-heavy-v1/`](experiments/augmentation-heavy-v1/).
Native-fog conclusions and the selected comparison sheet are stored in
[`docs/experiments/native-fog-v1/`](experiments/native-fog-v1/).
Raw study bundles remain ignored under `outputs/experiments/`.

## Placement rejection diagnostics

Run the production-path landing study:

```powershell
uv run python -m dataset_generator_m1 experiment placement `
  --config examples/configs/landing_minimal.yaml `
  --samples 200 `
  --qa-samples 20 `
  --output-dir outputs/experiments/landing-placement
```

The pool stores bounded object-attempt evidence. The study adds spatial heatmaps and failed-plan
overlays without changing the planner. Interpret rates with their attempt denominators; shares of all
rejections are not conditional rejection rates. Raw output remains ignored. Reviewed conclusions and
one compact contact sheet may be promoted under `docs/experiments/`.

## Asset-disjoint feasibility

Analyze a validated pool without creating an export tree:

```powershell
uv run python -m dataset_generator_m1 export `
  --pool outputs/pool-a `
  --strategy asset-disjoint `
  --splits train=0.8,val=0.1,test=0.1 `
  --analyze-only `
  --output-format json
```

The reviewed [landing/manometro study](experiments/asset-disjoint-v1/README.md) compares current hash,
greedy sample-balance, and greedy class-balance assignments. It found connectivity—not allocator
choice—to be the limiting factor. Raw study pools remain ignored.
