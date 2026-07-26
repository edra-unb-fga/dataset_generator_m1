# Appearance Effects

Appearance effects change pixels only. Geometry, masks, assets, sampling, annotations, and output dimensions are controlled by other composer subjects. Every effect must have a stable ID inside its stage so its activation and parameters use an independent deterministic random stream.

## Native effect

### `AtmosphericFog`

Depth-dependent haze following the public Albumentations scattering model:

```text
output = image × exp(-density × depth) + fog_color × (1 - exp(-density × depth))
```

Parameters:

- `density_range`: ordered non-negative pair; sampled density is traced.
- `fog_color`: three channel values from 0 to 255.
- `depth_mode`: `linear`, `diagonal`, or `radial`.

The local effect is deterministic, records its sampled parameters and duration, and preserves foreground alpha bit-for-bit. See the [official AtmosphericFog documentation](https://albumentations.ai/explore/transform/AtmosphericFog/docs/).

`AtmosphericFog` is not equivalent to `RandomFog`. Atmospheric fog applies smooth depth-dependent scattering; RandomFog creates patch-like fog regions and has shown substantially higher and more variable local cost.

## Albumentations effects

The installed backend currently supports the following catalog-visible transforms through the same traced pipeline:

- color and exposure: `HueSaturationValue`, `RandomBrightnessContrast`, `RandomGamma`, `PlanckianJitter`, `Illumination`, `PlasmaBrightnessContrast`;
- blur and noise: `GaussianBlur`, `MotionBlur`, `GaussNoise`, `AdditiveNoise`, `SaltAndPepper`;
- lighting and shadow: `PlasmaShadow`, `RandomSunFlare`;
- weather: `RandomFog`, `RandomRain`.

Exact parameters are validated against the installed Albumentations version before output creation. Use `catalog show` for reviewed bundles and the guided configurator for stage-specific construction. Path-only custom YAML is allowed but is treated as undocumented until explicitly promoted and reviewed.

## Controlled fog comparison

`examples/experiments/fog_mode_study.yaml` compares no appearance, all three native depth modes, and patch-based RandomFog while holding the scene plan constant:

```powershell
uv run python -m dataset_generator_m1 experiment augmentations `
  --config examples/configs/landing_minimal.yaml `
  --matrix examples/experiments/fog_mode_study.yaml `
  --output-dir outputs/experiments/landing-fog-modes
```

Interpret timing causally only within the same recorded environment. Slow effects remain available; reviewed findings become warning and ETA evidence rather than removal rules.
