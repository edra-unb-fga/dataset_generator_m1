# Ground scale, sunlight, UVs and material variants

Open the [combined visual report](index.html), the [18-cell paired report](first-pass.html),
its [measured JSON](first-pass.metrics.json), [direct blend comparisons](extra-comparisons.json),
or the [controlled UV check](uv-check.html).
[Provenance](provenance.json) records the sealed source/input and verified result archive.

## What this screen establishes

The first L4 batch completed 18/18 cells at 640 × 640, 32 samples, using two reference scenes.
It includes the two-metre fallback, fixed 0.5/1/1.5 view-relative spans, five material treatments
on Ground068 and Asphalt012, an indoor pair and two directional-normal fixture cells. These reuse
scene intent; 18 rendered cells are not 18 independent scenes. Every recorded per-scene mask
signature matched. The report independently compares actual arrays in 12 designated image pairs.

The separate local UV check verifies Blender's derived tangent basis at 0° and 90°. A corrected
nadir render pair gives grayscale MAE 0.51/255 and correlation 0.981 over 41,904 unmasked ground
pixels after the expected rotation. The original oblique comparison used the wrong light rotation
and remains explicitly inconclusive in the [diagnostic account](uv-check.md).

## Findings from the first batch

| Question | Observation and implication |
| --- | --- |
| Does view-relative scale avoid the fallback repetition? | Yes in these views: requested 0.5/1/1.5 spans were achieved exactly, with tile widths 12.563/6.282/4.188 m and guaranteed coverage. The two-metre fallback repeats conspicuously. Lower spans also enlarge surface features; this is a framing control, not physical-scale calibration or an anti-tiling algorithm. |
| Is explicit sunlight exercised? | Every open cell uses a SUN light with angular size 0.00918 rad, plus HDR strength 0.15. Its directional model is distinct from point/area lights. Thin pads cast little visible shadow; this does not test ambient-shadow distribution coverage. |
| Do material maps change the image? | They are connected and change the image. Color-only vs full maps gives background RGB MAE 1.95 on Ground068 and 0.60 on Asphalt012. These modest effects depend on framing, light and normal strength; they do not establish that maps are unnecessary. |
| Does blending add diversity? | Coherent blending changes background color/texture noticeably (MAE 5.61 and 6.55 versus each full baseline). Coherent vs RGB-only blending differs by only 0.96 and 0.50 levels in the ground region, so these views alone give little evidence of a large perceptual advantage from synchronizing all maps. |
| Is the indoor lighting qualified? | No. The explicit 500 W area emitter and automatic 800 W ceiling area emitter produce bright pools and some washed-out labels. Both material cells share this illumination. It is not an isolated one-light comparison. |

The indoor pair deliberately reuses the same grass material for attribution. It is a material/light
diagnostic, not a proposed ordinary indoor family; use explicit ground eligibility for realistic floors.

Pixel differences are descriptive changes in 8-bit RGB, not realism or detector-utility scores.
Color-only replaces both textured roughness and normals; that comparison does not isolate their
individual contributions. Blender normals perturb shading, not the flat ground mesh. Displacement,
ambient-occlusion maps and asset physical dimensions are not applied automatically. No calibrated
BRDF, real-image comparison, trained detector or high-sample convergence study was performed.

## Implementation and reproduction

The [ground material guide](../../GROUND_MATERIALS.md) documents independent `ground_mapping`,
mesh UVs with matching tangent orientation, primary/donor selection and the explicitly marked stress
variants. Coherent blending shares a mask across color, roughness and decoded shading normals;
it is a procedural approximation, not a simulation of physical material layers. `blend_amount`
multiplies noise, so 0.5 does not mean a uniform 50% donor fraction.

The tracked [study workflow](../../../experiments/blenderproc/studies/ground-material-study/README.md)
and matrices bind reproduction to inputs and source fingerprints. Build a fresh licensed input
bundle, run preparation assertions, then use the bounded controller with adaptive guards,
checksum-verified retrieval and automatic shutdown. Raw data, full images, failures and interrupted
local attempts remain in ignored `outputs/experiments/ground-material-20261029/`.

The first batch used 1 m panels, 3 mm thick. Its remote work took 327.4 s; controller start through
confirmed shutdown took 362.4 s. Individual command times were 5.43–8.77 s and include startup/probe
work. The account balance snapshots changed 156.76 → 156.63 CU, with an observed active rate of
1.94 CU/hour; billing delay and allocation timing prevent treating this as exact metered cost.
These small isolated cells are not a sustained throughput benchmark.

## Contextual follow-up

A [six-cell follow-up](context.html) completed 6/6, with five designated variant/baseline image pairs
and exact visible/full mask arrays. It holds sunlight, pad wear and three ambient casters fixed while
comparing full maps, normals disabled, UV rotation/offset, stronger coherent blending, stronger
RGB-only blending and donor mismatch. It explicitly uses 5 mm panels. Compare materials within this
follow-up, since its geometry and context differ from the first batch.

| Variant vs context-full | Ground RGB MAE / 255 | Interpretation |
| --- | ---: | --- |
| Normals disabled (1 → 0) | 4.64 | Surface shading changes without geometry changes; this isolates normal strength under this lighting. |
| UV 45° with offset (0.37, 0.61) | 13.03 | Coherent movement of the real texture is a strong source of visual diversity. |
| Coherent blend, amount 1 | 9.06 | Stronger color and texture changes remain visible with wear and shadows present. |
| RGB-only blend, amount 1 | 9.25 | Similar broad appearance, with a different ground response to illumination. |
| Donor roughness/normal mismatch | 5.18 | A distinct response is possible while retaining primary color, but physical coherence is intentionally broken. |

Coherent vs RGB-only blending differs by 2.92 levels over ground pixels in this contextual scene.
Their large-scale appearance is still close. These numbers describe magnitude, not preference or
training utility. Pad pixel changes are much smaller (0.25–0.87 levels), so this study primarily
diversifies ground/context rather than demonstrating improved plastic-pad reflections.

The long, consistent shadow direction provides an explicit sunlight example. Rectangular shadows
are intended distractors. A conspicuous dark square near the top of the frame appears caster-related;
its exact origin was not isolated. The simple caster geometry and its visual footprint deserve review,
without treating the presence of dark shadows as a failure. Dirt marks are visible on close inspection.

Remote follow-up work took 179.7 s, with verified retrieval and confirmed shutdown. Balance snapshots
changed 156.63 → 156.52 CU. Both L4 batches used the same renderer source and are separately sealed.
The combined 24 GPU cells reuse two reference scenes; four local renders additionally diagnose UV
behavior. This is controlled engineering evidence with very limited independent scene coverage.

## Recommended use and next decisions

Use explicit view-relative mapping when repeated patterns are unwanted, and vary coherent UVs before
adding more complex mixing. Keep real material map sets available: their effect can become stronger
with different incidence and normal strength. Coherent blending is the preferable candidate for
material-consistent experiments; RGB-only and donor-mismatch modes stay explicitly experimental.
No production appearance distribution is automatically changed by this screen.

The next useful realism work is still conditional environment/material selection and better indoor
light/material distributions. Further pad-specific reflection studies need controlled roughness,
light direction and reference examples. Independent per-map UV de-registration, true displacement,
measured physical texture scale, broad unseen-scene qualification and detector evaluation remain
outside this delivery. The current mesh UV transform moves maps together; mismatch mode changes the
map donor rather than giving each map an independent transform.
