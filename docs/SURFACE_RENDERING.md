# Experimental planar surfaces

## Coherent profile choices for review

These profiles are opt-in, uncalibrated candidates; no family default is changed.
Select the scene and appearance independently, and inspect the fully resolved
composer because explicit inline overrides remain in force.

| Choice | Scene profile | Appearance profile | Purpose |
| --- | --- | --- | --- |
| Earlier coherent | `coherent-varied` | `coherent-varied` (`coherent-varied-manometro` for gauges) | Paired reference with shared shade and restrained wear. |
| Balanced capture | `coherent-varied` | `coherent-balanced` (`coherent-balanced-manometro` for gauges) | Existing coherent surface and shared shade with frequent, weighted motion blur. |
| Surface variation | `coherent-varied` | `coherent-surface-varied` (`coherent-surface-varied-manometro` for gauges) | More visible, still qualitative existing wear. |
| Challenging | `coherent-challenging` | `coherent-challenging` (`coherent-challenging-manometro` for gauges) | Wider shade and wear ranges plus stronger exposure variation. |

`WeightedMotionBlur` is one final-RGB transform: activation is independent of
surface wear, and only one weighted odd-sized kernel is sampled when it activates.
The experimental balanced settings at 640px are 40/20/10% for 3/7/15px kernels
on landing and landing-pad and 40/15/5% on manometro; other outcomes remain
unblurred. Kernels are specified in output pixels, not automatically calibrated
to resolution, camera motion or exposure. The severe setting intentionally can
obscure small markings. Actual realized frequencies vary with seed and sample size.
Old explicit profiles and composers that omit appearance retain their prior behavior.

Use `examples/configs/landing-pad_surface.yaml` through the normal resolve, preview, preflight and generate commands. Existing composers retain their selected effects. No physically calibrated realism or detector gain is claimed.

`scene.lighting` is optional (omission disables it). Its probability (default .8), gain range [.85,1.10], gradient amplitude [.05,.25] and tint bound .025 sample one constant/linear irradiance field in scene coordinates. Gain is bounded [.1,2], gradient [0,1], tint [0,.1]. Inverse shared homography evaluates the same field for all surfaces. Texture affine rotation leaves the lighting field fixed. Modulation uses linear RGB after composition and before capture effects, with bounded row workspaces. It cannot remove baked shadows from photographs. `source_assumption` records `unknown`, `baked` or `unlit-approximation`; it is a declaration, not an inferred property.

Foreground-only native `SurfaceWear` accepts `fade`, `dirt`, `scratches`, `marks` (0–64), and `scratch_width` relative to source width. The normalized fixed-width lattice (512 wide, height capped at 2048) makes the marks independent of ordinary source resolution. Wear changes RGB before rotation/projection and preserves alpha exactly. It models faded pigment, dirt and scratches qualitatively, not holes or material damage. Pristine source assets stay untouched. Stable effect IDs own deterministic streams; the shared field uses a separate scene-lighting stream.

The shipped `surface-camera` preset combines mild wear with restrained exposure, motion and compression, avoiding independent surface-light/shadow stacks. Configuration is uncalibrated. Try fade .03/.06/.2, dirt .08/.18/.5, scratches .05/.12/.4 for mild/moderate/forced engineering checks; forced activation is diagnostic.

Pool records retain realized seeds, sampled parameters and exclusive scene-lighting timing, alongside ordinary foreground effect traces. Cost identities include scene settings; preflight marks unmeasured enabled scene effects and budgets their temporary memory. Renderer semantics `planar-surface-v3.2` require a fresh pool after this upgrade; old pools remain inspectable and exportable. Same-version resume remains supported.

The core 2D renderer does not simulate normal/roughness response, physical sun angles, cast shadows, specular response or raised targets; richer physical behavior remains tracked in #62/#63. The optional host map preparation below supports controlled 3D material studies without adding a physical renderer to the core. Future BlenderProc comparisons (#64) must match conditions and annotation policies, distinguish textured planes from physical scenes, and include cold start, scene reuse, output/QA and asset preparation costs. Equal dataset-size and equal generation-time comparisons answer different questions. This round installs no Blender runtime.

## Procedural occlusion

`examples/configs/landing-pad_occlusion.yaml` adds optional `scene.occlusion`. Configure probability [0,1], kind (`blade`, `debris`, `mixed`), count range (0–64), length/width fractions of camera width (up to 1.2/.3), opacity range [.1,1], and `min_visible_support` [0,1] (starter .25). The independent stream places bounded unlabeled strips/irregular polygons in the scene plane and projects them through the target/ground homography. Their appearance resembles simple blades and debris; it is not a validated vegetation model. They composite above targets, before common illumination/capture. No imported occluder catalog role or cast shadows are added.

Targets whose transformed alpha supports intersect above the family threshold are not composited: later instances are dropped, with a typed overlap rejection. Sub-threshold edges may overlap. Full target alpha precedes external occlusion. Visible alpha is its remaining contribution. `visible_support_fraction` counts visible/full pixels above the family alpha threshold **within the image**; it is independent of the historical frame-clipping `visible_bbox_fraction`. Final boxes derive from visible masks. Fully hidden and below-floor targets lose annotations and archive entries with typed rejections. Best-effort retains survivor IDs; require-count rejects incomplete candidates after occlusion. Accidental empty positives are rejected; intentional negatives remain valid. The default `visibility_policy: legacy` can leave below-floor target pixels as unlabeled fragments. Opt into `visibility_policy: reject-visible-below-floor` to reject the entire candidate when any below-floor target retains above-threshold visible contribution. Fully hidden targets may still be omitted; below-threshold residual contribution can remain.

Occluder polygons/opacity enter geometry signatures; appearance-only study invariants remain strict. Scene records include layer coordinates/colors, stream seeds, output support and the acceptance floor. Exclusive occlusion/annotation timings and advisory temporary-memory estimates include enabled work. Workspace is streamed per layer rather than retained per occluder. No new default renderer features activate by omission.

## Optional alpha-correct resampling

`inline.scene.foreground_resampling: premultiplied` filters RGB weighted by alpha during foreground
rotation, resize and perspective projection, then returns straight RGBA. Integer alpha, geometry,
coverage masks and annotations remain unchanged. This prevents fully transparent hidden RGB from
contaminating visible edges. It does not change encoded-RGB composition or simulate lighting.

The default `legacy` path retains historical pixels and contract identities when omitted. Corrected
mode participates in strict and normalized generation identities and cannot resume a legacy pool.
Changing a composer file explicitly still changes its strict source identity. Use a fresh pool with
`examples/configs/landing-pad_premultiplied.yaml`; existing builtin bundles remain untouched.
The estimator includes the enabled float filtering workspace. See `REALISM_ROUND_TWO.md` for the
separate scheduler and optional physical-rendering scope.


## Shared wear maps and conditional environmental shade

The host-only `prepare_wear_maps(artwork, params, seed, output_dir, *, roughness=.5)`
helper shares `SurfaceWear` fields with the optional 3D harness. It accepts RGB/RGBA
arrays or image paths and writes registered, source-sized PNG albedo, roughness and
height maps. The returned manifest includes configuration, field seed, dimensions,
channel encodings, hashes and the top-left artwork-UV convention. Albedo follows
the existing encoded-RGB wear blend exactly; RGBA alpha is unchanged. Roughness
and height are linear data. Height is a qualitative bump input, with renderer-side
amplitude recorded separately; it does not change the flat panel silhouette.

The opt-in `landing-pad_surface-pristine.yaml`, `landing-pad_surface-moderate.yaml`
and `landing-pad_surface-stress.yaml` composers share the same capture stack and
scene settings. The pristine composer omits local wear; moderate and stress enable it.
The severity study separately records a zero-strength operation as a paired control;
its cost is not the same as omitting the operation. Stress is an explicit diagnostic, not an
ordinary realism recipe. The separate `landing-pad_environmental-shade.yaml`
composer adds this candidate beneath `inline.scene.lighting`:

```yaml
shade:
  probability: 0.7
  strength: [0.12, 0.4]
  radius_fraction: [0.12, 0.45]
```

One soft elliptical Gaussian attenuates linear RGB across all composed surfaces.
Its center, axes, angle and strength are sampled in normalized scene coordinates
from an independent `scene-environmental-shade` stream. Shade activation is independent
of the parent gain/gradient field probability. Gain/gradient/tint draws,
geometry, alpha, masks and annotations are unchanged. The inverse shared
homography carries the field through the global camera transform before final
capture effects. Workspace is bounded to 128 output rows. Absence, probability
zero, or zero maximum strength disables shade and preserves old normalized lighting
serialization; changing a source composer still changes strict source provenance.
Bounds are strength 0–.8 and normalized radii .04–1.2. This is a qualitative
approximation of environmental shade; it cannot infer scene geometry, remove baked
photographic shadows, or produce physical contact shadows. Keep it experimental
unless paired visual evidence supports retention. Existing defaults remain unchanged.


## Experimental linear-light composition

Set `inline.scene.compositing: linear-srgb` to blend both targets and procedural occluders in linear
light. The default is `legacy`; the new option changes pixel colors without changing coverage, alpha,
geometry or acceptance. Each layer is encoded back to 8-bit sRGB before the next layer, so this is
not a single high-precision whole-scene accumulation. The initial review supports opt-in testing, not
a realism or detector-benefit claim. See `experiments/camera-environments-v1/README.md`.


## Experimental local foreground context

`inline.scene.foreground_context` enables a bounded colour adjustment based on the
projected background near each target. It samples local background outside the target,
then applies a spatially uniform sRGB brightness and colour shift to the target. It is a
qualitative adaptation, not physical illumination, and cannot remove baked lighting or
create material response. Alpha, target geometry and background pixels remain unchanged.
An object-specific seed controls the configured probability and strength range; sampled
settings and shifts are recorded in scene evidence. If no local background is available,
the foreground remains unchanged.

The `landing-pad_context-restrained.yaml` and `landing-pad_context-broad.yaml` examples
are uncalibrated candidates. Broad settings may noticeably alter the target colours.
Neither is a new default, and visual similarity or detector improvement has not been
established. `scripts/study_foreground_context.py` and its saved study matrix support
paired comparison with a separate reserved seed; both phases reuse the same asset catalog.

The opt-in `builtin:scene/coherent-candidate` combines premultiplied resampling,
background context and a shared illumination field while retaining standard geometry.
Context is always attempted, with strength [.35,.65], radius .12, brightness cap .12
and per-channel chroma cap .06. The field uses probability .8, gain [.9,1.05],
gradient [.02,.12] and tint .015. These caps are deliberately much lower than the
previous broad treatment, which produced purple and washed-out targets. They are
uncalibrated engineering choices rather than evidence that the result is more realistic.
Set `scene: builtin:scene/coherent-candidate` and
`appearance: {preset: builtin:appearance/coherent-candidate}` in a new composer to
try the coordinated treatment. Its wear probability is .8 with fade .08, dirt .24,
scratches .16 and 16 marks; restrained whole-frame exposure, motion blur and JPEG
compression complete the candidate. Existing composers keep their selected profiles.
Review every family separately before promotion.
See `experiments/foreground-context/coherent-candidate.json` for a saved ablation.

`builtin:scene/coherent-refined` and `builtin:appearance/coherent-refined` are a
second paired-review variant: initial landing crops showed conspicuous circular dirt
in the first candidate. The refined appearance lowers wear to probability .65, fade
.03, dirt .06, scratches .04 and six marks. The refined scene adds optional shared
shade (probability .5, strength [.08,.18], radii [.2,.45]). The shade is a common
field, not a physical contact shadow. Both variants remain experimental.

### Opt-in directional shade

`scene.lighting.directional_shade` adds an independent qualitative slab attenuation
in normalized scene coordinates after foreground/background composition and before
capture. `probability` is in [0, 1]; ordered `strength` is [0, .8], `width` is
[.01, 1.5], `softness` is [0, .5], `offset` is [-1, 1], and `angle_degrees` is
[-360, 360]. Both endpoints are bounded in the generated JSON Schemas; runtime
also rejects reversed pairs, which ordinary JSON Schema cannot generally express.
`width`, `softness` and `offset` use normalized scene coordinates:
the signed position is `cos(angle) * (scene_x / canvas_width - .5) + sin(angle)
* (scene_y / canvas_height - .5)`. Zero softness gives a hard edge; otherwise
smoothstep transitions across the given edge width. It samples a separate random
stream, records parameters with the scene effect, and shares the existing scene
homography. It leaves masks and annotations unchanged. Omitted or disabled shade
preserves the existing serialized profile and rendering. Inline disabling survives
profile merge. This infinite slab is a procedural approximation; it does not infer a
caster, height, contact shadow or baked lighting, and is not a calibrated physical
lighting model. `builtin:scene/coherent-directional` is an experimental scene
profile paired for review with `builtin:appearance/coherent-refined`; no default
profile uses it.

Directional shade also accepts `shape: rectangle` or `shape: ellipse` for finite,
independently sampled silhouettes; omission keeps the original infinite `band` and
its random draws. `length` is the full extent along the band (scene fraction,
ordered range .01–1.5, default [.3,1]); `longitudinal_offset` sets its center
along that axis (ordered range -1–1, default [-.3,.3]). The existing width,
offset, angle, strength and bounded softness controls still apply. Shapes are
analytic scene-plane approximations, not physical caster geometry. Choose shapes
explicitly for controlled studies; no mixed-shape production preset is promoted.
