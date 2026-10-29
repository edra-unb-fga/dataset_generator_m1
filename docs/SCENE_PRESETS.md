# Experimental scene presets

An annotation family defines the target and annotation rules in the core 2D generator. A scene preset
selects visual context for the separate optional BlenderProc pilot. Presets do not change the core 2D
defaults. They are experimental engineering controls, not calibrated realism or evidence of detector
performance.

The preset helper offers `open`, `outdoor` and `indoor`:

```bash
uv run python scripts/generate_scene_presets.py list
uv run python scripts/generate_scene_presets.py list --details
uv run python scripts/generate_scene_presets.py resolve --config configs/local/pilot-template.json --preset outdoor --output configs/local/outdoor-resolved.json
uv run python scripts/generate_scene_presets.py prepare --config configs/local/pilot-template.json --preset indoor --output outputs/experiments/indoor-preset
```

For a first journey, follow the [pilot setup](../experiments/blenderproc/README.md) to prepare a
reference pool, artwork, grounds, environments and renderer. Copy
[`pilot-fast.example.json`](../experiments/blenderproc/pilot-fast.example.json) to
`configs/local/pilot-template.json`, update **all** its paths (relative paths are relative to the copied
config), reduce `treatments` to exactly one template, and set `quality_treatments` to `[]`. Set the
number of scenes deliberately. Run `list` and then `prepare` above; proceed with the pilot's standard
`render`, `export` and `report` commands against `outputs/experiments/indoor-preset`. Preparation does
not render. Choose a fresh output path for each run.

`resolve` embeds the versioned preset, resolves asset paths, and refuses to overwrite its output. To
customize, copy one of the strict JSON files in
[`experiments/blenderproc/scene-presets/`](../experiments/blenderproc/scene-presets/), edit it, and
replace `--preset indoor` with `--preset-file configs/local/my-preset.json`. The choices are mutually
exclusive. Presets expose weighted lighting and ground eligibility; sun direction, angular size,
power and color; lamp type, count, geometry and color; caster types and dimensions; and independent
wall and ceiling material controls. Sun angular size is in radians; point/spot size is a radius, with
spot cone and blend specified separately. Indoor lamp positions are fitted with their emitter extent
inside the actual room or omitted if too large. Casters crossing indoor boundaries or intersecting
the panel are omitted with a recorded reason. `wall_texture` defaults to
`none`; `base` explicitly retains the base texture and overrides the sampled wall color.

Each scene samples choices independently from the one template treatment, producing one fast job
without diagnostics. The pilot's source assets and normal run/export workflow are still required;
presets do not guarantee independent dataset splits. Current synthetic examples can have indoor
hotspots and washed-out targets; see the [procedural visual screen](experiments/procedural-scenes-v1/README.md)
and [historical exploration](experiments/realism-exploration-v1/README.md). The procedural report
distinguishes the sealed L4 source from the final indoor safeguards. Review outputs and annotations
before using a dataset.

## What the preset controls

| Control | Current behavior |
| --- | --- |
| Environment enclosure | `open` has no walls; `outdoor` has perimeter walls; `indoor` adds a ceiling. Room size adapts to the camera and targets. `wall_heights_m` controls outdoor walls; indoor height comes from room bounds. |
| Grounds | `ground_weights` selects indices in your supplied material catalog. `null` allows every supplied ground, including grass indoors. The stock files do not infer material semantics: bind appropriate grounds explicitly for a coherent indoor dataset. |
| Lights and materials | Bounded per-scene sampling of explicit lamp/sun controls, pad roughness, wall/ceiling colors and roughness. Wall and ceiling colors vary independently, without measured real-room calibration. |
| Casters | Weighted shape, count and dimension choices. Set count to `[0, 0]` for no added casters; use only `cylinder` for poles. `sphere` scales to an ellipsoid when height differs from width. Shadows may miss the target or be invisible; their presence is not forced. |
| Appearance and atmosphere | Wear, dirt, glare-related material settings, fog and other existing treatment effects come from the single template. They are not independently sampled by these presets. |
| Camera | Existing `camera_study` controls framing and pose. Presets do not change its distribution. Mostly top-down views can hide the distinction between open and walled environments. |

The resolved job contains sampled controls; renderer evidence records any adjusted or omitted
geometry. Reproducibility uses the preset version, seed, sequence offset, asset fingerprints and
source identity. Keeping the same source/assets and using `scene_offset` allows a sequence to be
prepared in chunks. This is a first reusable procedural interface; asset-semantic constraints,
calibrated light/material distributions and weighted mixtures of several scene presets remain future
work. For now, prepare separate preset runs deliberately instead of treating the three stock files
as a validated automatic dataset mixture.

`environment_geometry_settings` can be supplied directly with a procedural preset; an
`environment_mix` is not required because the preset supplies the enclosure type.

Ground material variants and view-relative texture scaling are separate experimental controls; see
[ground materials](GROUND_MATERIALS.md) for their interaction with preset-selected grounds.
