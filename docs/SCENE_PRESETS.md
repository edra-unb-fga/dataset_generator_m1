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
| Appearance and atmosphere | Single presets inherit the template treatment. A mixture may supply treatment overrides per member, coordinating wear and haze with its selected enclosure. |
| Camera | Existing `camera_study` controls framing and pose. Presets do not change its distribution. Mostly top-down views can hide the distinction between open and walled environments. |

The resolved job contains sampled controls; renderer evidence records any adjusted or omitted
geometry. Reproducibility uses the preset version, seed, sequence offset, asset fingerprints and
source identity. Keeping the same source/assets and using `scene_offset` allows a sequence to be
prepared in chunks. This is a first reusable procedural interface; calibrated light/material distributions remain future work. The optional mixture described below is an uncalibrated candidate.

`environment_geometry_settings` can be supplied directly with a procedural preset; an
`environment_mix` is not required because the preset supplies the enclosure type.

Ground material variants and view-relative texture scaling are separate experimental controls; see
[ground materials](GROUND_MATERIALS.md) for their interaction with preset-selected grounds.

## Experimental balanced mixture candidate

[`pilot-balanced-candidate.example.json`](../experiments/blenderproc/pilot-balanced-candidate.example.json)
selects open, outdoor, and indoor presets with equal weights and couples each choice to its haze
treatment. Independently weighted clean reflective, lightly worn and worn material states are recorded
per job and can be edited in the candidate. The embedded presets retain their own lighting, casters and materials. It uses a 5 mm
panel and view-relative ground mapping with 0.5–1.5 sampled spans. Mesh UV coordinates keep texture
maps and normal-map tangent orientation coherent. It is an opt-in candidate, not a promoted default. Choices are random weights, not exact quotas.
Copy the file to a local config, update every path, and ensure the catalog order matches its explicit
ground indices: the example uses ground 0 and asphalt 1 outdoors and concrete 2 indoors; open and
outdoor also allow concrete. The candidate binds indices to expected manifest asset IDs, which preparation checks against the
supplied catalog. Material semantics are not inferred; changing an eligible material requires deliberate
review of both its index and ID. Legacy entries without asset IDs retain index-only behavior. `ground_weights: null` allows every ground and emits a warning.

Prepare using `uv run python scripts/blenderproc_pilot.py prepare --config configs/local/balanced.json
--output-dir outputs/experiments/balanced-candidate`, then use the normal render, export and report
commands in the pilot README. Mix members embed full presets and positive weights; edit those and the
strict treatment overrides as needed. Preset-owned lighting, roughness, environment, shadow, caster
and lamp fields cannot be overridden per member; material states own roughness and wear. When
material states are supplied, a member wear override is rejected. A fixed
ground-material primary must be eligible for every possible selected preset. Scene offsets preserve the selected mixture sequence. Review
rendered scenes and annotations before promoting or using the candidate.
