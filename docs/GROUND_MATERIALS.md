# Experimental physical ground materials

These controls apply to the optional BlenderProc harness. They are opt-in study controls; the core 2D
generator and default pilot behavior are unchanged. They are not calibrated materials or promoted
production distributions. Begin with [pilot setup](../experiments/blenderproc/README.md), including
licensed, hash-verified material manifests and all referenced maps.

## Mapping and scale

A `ground_mapping` object on the pilot config opts into view-relative UV mapping. Its defaults are:

```json
"ground_mapping": {
  "ground_spans": [0.5, 1.5],
  "extent_bounds_m": [40, 500],
  "tile_bounds_m": [0.1, 500],
  "footprint_margin": 1.1
}
```

The requested span count is sampled deterministically per seed and scene sequence; tile size is
estimated from the central ground-view width divided by this count and clamped to the configured
bounds. The plane extent is also bounded. Saved diagnostics record requested and achieved spans,
clamping and coverage; a horizon fallback or extent clamp means coverage is not guaranteed. Rotation
and offset still come from the treatment's `uv_rotation_degrees` and `ground_uv_offset`.

Without `ground_mapping`, existing camera-study `material_mode` remains available: `view-relative`
uses camera-study spans, while `fixed-physical` uses the treatment's `uv_scale_m` as tile size. Without
a camera study, the legacy plane uses its normal fixed extent and `uv_scale_m`. Explicit
`ground_mapping` takes precedence over camera-study material mode and always uses view-relative spans.
Adding `ground_mapping` or a `ground_material` treatment opts into UV coordinates on the mesh itself,
so normal-map tangent orientation follows rotation. The untouched legacy path uses the shader's
mapping node. These paths are not promised pixel-identical.

## Material variants

Place `ground_material` inside a treatment. For example, use this fragment with at least two supplied
grounds and matching maps:

```json
"ground_material": {
  "mode": "coherent-blend",
  "primary_index": 0,
  "donor_index": 1,
  "blend_scale": 2,
  "blend_amount": 0.5,
  "blend_seed": 0
}
```

Indices address the ordered pilot `grounds` list. `primary_index` defaults to null, retaining the
selected scene ground (including procedural preset selection); a specified primary overrides that
selection. A donor is mandatory for blend or mismatch modes, forbidden otherwise, and must differ
from each selected primary. When using a donor, set a distinct explicit primary to avoid a sampled
primary/donor collision. Preparation validates map availability and hashes before rendering.

| Mode | Maps applied |
| --- | --- |
| `color-only` | Primary color; shader roughness is its constant default and no normal map is connected. |
| `full` | Primary color, roughness and normal. |
| `coherent-blend` | A shared deterministic noise mask blends primary and donor color, roughness, and decoded normalized shading normals. |
| `rgb-blend-stress` | The same mask blends color only; roughness and normal remain primary. |
| `donor-mismatch-stress` | Primary color with donor roughness and normal. |

The stress variants intentionally break material coherence to expose failure modes; they are not
recommended distributions. `blend_scale` controls noise scale (default 2), `blend_amount` multiplies
the mask (default 0.5), and `blend_seed` offsets its deterministic pattern (default 0). Masks are
shared across channels in coherent blending. Map files are color, roughness and normal; displacement
is not applied to ground geometry. Ground normal strength follows `ground_normal_strength` when set,
otherwise `normal_strength`.

For paired studies freeze the source/configuration and compare saved matrices, geometry and mask
checks alongside full images and crops. See the [study workflow](../experiments/blenderproc/studies/ground-material-study/README.md)
for readiness and evidence. Do not infer real-image or model performance from visual examples.
