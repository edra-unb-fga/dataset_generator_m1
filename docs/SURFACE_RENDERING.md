# Experimental planar surfaces

Use `examples/configs/landing-pad_surface.yaml` through the normal resolve, preview, preflight and generate commands. Existing composers retain their selected effects. No physically calibrated realism or detector gain is claimed.

`scene.lighting` is optional (omission disables it). Its probability (default .8), gain range [.85,1.10], gradient amplitude [.05,.25] and tint bound .025 sample one constant/linear irradiance field in scene coordinates. Gain is bounded [.1,2], gradient [0,1], tint [0,.1]. Inverse shared homography evaluates the same field for all surfaces. Texture affine rotation leaves the lighting field fixed. Modulation uses linear RGB after composition and before capture effects, with bounded row workspaces. It cannot remove baked shadows from photographs. `source_assumption` records `unknown`, `baked` or `unlit-approximation`; it is a declaration, not an inferred property.

Foreground-only native `SurfaceWear` accepts `fade`, `dirt`, `scratches`, `marks` (0–64), and `scratch_width` relative to source width. The normalized fixed-width lattice (512 wide, height capped at 2048) makes the marks independent of ordinary source resolution. Wear changes RGB before rotation/projection and preserves alpha exactly. It models faded pigment, dirt and scratches qualitatively, not holes or material damage. Pristine source assets stay untouched. Stable effect IDs own deterministic streams; the shared field uses a separate scene-lighting stream.

The shipped `surface-camera` preset combines mild wear with restrained exposure, motion and compression, avoiding independent surface-light/shadow stacks. Configuration is uncalibrated. Try fade .03/.06/.2, dirt .08/.18/.5, scratches .05/.12/.4 for mild/moderate/forced engineering checks; forced activation is diagnostic.

Pool records retain realized seeds, sampled parameters and exclusive scene-lighting timing, alongside ordinary foreground effect traces. Cost identities include scene settings; preflight marks unmeasured enabled scene effects and budgets their temporary memory. Renderer semantics `planar-surface-v3.1` require a fresh pool after this upgrade; old pools remain inspectable and exportable. Same-version resume remains supported.

The core 2D renderer does not simulate normal/roughness response, physical sun angles, cast shadows, specular response or raised targets; richer physical behavior remains tracked in #62/#63. The optional host map preparation below supports controlled 3D material studies without adding a physical renderer to the core. Future BlenderProc comparisons (#64) must match conditions and annotation policies, distinguish textured planes from physical scenes, and include cold start, scene reuse, output/QA and asset preparation costs. Equal dataset-size and equal generation-time comparisons answer different questions. This round installs no Blender runtime.

## Procedural occlusion

`examples/configs/landing-pad_occlusion.yaml` adds optional `scene.occlusion`. Configure probability [0,1], kind (`blade`, `debris`, `mixed`), count range (0–64), length/width fractions of camera width (up to 1.2/.3), opacity range [.1,1], and `min_visible_support` [0,1] (starter .25). The independent stream places bounded unlabeled strips/irregular polygons in the scene plane and projects them through the target/ground homography. Their appearance resembles simple blades and debris; it is not a validated vegetation model. They composite above targets, before common illumination/capture. No imported occluder catalog role or cast shadows are added.

Full target alpha precedes later target/external occlusion. Visible alpha is its remaining contribution. `visible_support_fraction` counts visible/full pixels above the family alpha threshold **within the image**; it is independent of the historical frame-clipping `visible_bbox_fraction`. Final boxes derive from visible masks. Fully hidden and below-floor targets lose annotations and archive entries with typed rejections. Best-effort retains survivor IDs; require-count rejects incomplete candidates after occlusion. Accidental empty positives are rejected; intentional negatives remain valid. Below-floor target pixels may remain in the image as unlabeled fragments, an explicit consequence of this acceptance policy to review against future real-label conventions.

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
