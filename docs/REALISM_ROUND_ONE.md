# Realism round one — implementation agreement

Approved on 2026-10-24 after a twenty-question design review. This document preserves the agreed
scope and future uses; unchecked items are not implemented capabilities.

## Delivery and acceptance

- [x] A: review and merge #51 → #53 → #54 → #55 → #58 → #60 in order, using merge commits.
- [x] A: preserve the existing local artwork/profile-study changes separately; rerun a
  representative baseline with the corrected artwork without rewriting historical studies.
- [x] B: offline detection **and instance-segmentation** evaluation, reference audits and projection checks.
- [ ] C: experimental shared 2D illumination and RGB-only procedural wear.
- [ ] D: procedural scene-plane occlusion, post-occlusion acceptance and exact annotation evidence.
- [ ] E: integrated paired studies, production measurements, reports and merged validated milestones.

Pads drive the examples; the core is family agnostic and landing/manometro remain regression controls.
Use small dependent PRs, resolve review findings, and merge only after relevant checks pass.
Existing defaults remain unchanged. New rendering features are usable opt-ins, not isolated prototypes.

There are no real target-scene labels, external predictions or calibration captures in the reviewed
project inputs. Completion therefore requires trustworthy synthetic fixtures, visual evidence and
performance measurements, **not** demonstrated real-world detector improvement. Real-data results must
remain unknown until supplied. No training or inference framework is added.

## Interfaces

`evaluate prepare|score|compare` normalizes COCO ground truth or repository pools/YOLO exports,
scores external COCO box/mask predictions, and compares compatible results. A prediction coverage
manifest distinguishes an image with no detections from an image never processed. Use locked
`pycocotools` through an optional `evaluation` extra; do not implement approximate custom COCO AP.

Prepared datasets retain stable IDs, original dimensions, hashes, domain, evaluation role, declared
annotation semantics, optional session/location metadata and explicit unknowns. Optional local pool
bindings are checked against source-run hashes before enriching exported lineage. Do not ingest
arbitrary third-party YOLO predictions in this round. Full real/synthetic and experiment provenance
remain distinct from scoring correctness.

Exact visible pool masks, thresholded at the recorded family alpha threshold, are the primary
synthetic segmentation reference. Report YOLO polygon fidelity separately, including holes and
disconnected components. Box conversion preserves half-open pixel coordinates. Report canonical
box/mask AP/AR, per-class support, measured-size slices, fixed-operating-point precision/recall and
bounded failure overlays. Diagnostic defaults: confidence 0.25 and IoU 0.50; canonical AP is separate.
Unknown or unsupported scores are unavailable, not zero. Compare dataset, coverage, class, task,
annotation and scorer identities before reporting differences.

`reference audit|project` validates reference manifests, reports image and target statistics, and
checks explicitly supplied intrinsics/world-to-camera transforms against planar target observations.
Use OpenCV camera coordinates, metric dimensions with explicit units, and a world Z=0 target plane.
Reject invalid transforms and points behind the camera. Record measured/configured/inferred/unknown
provenance. Sharpness/exposure proxies are observables, not estimates of sensor noise, optics or pose.
No fitting calibration, automatic effect tuning or physical-camera generation mode is included.

All workflows deliver portable image-first offline HTML and machine-readable JSON with relative
artifact links, inputs/provenance, activation coverage, warnings and limits. No dashboard expansion.

## Surface rendering

Composer schema v2 keeps its existing subjects. Optional typed `scene.lighting` and
`scene.occlusion` are disabled by omission. Native foreground `SurfaceWear` uses existing stable
effect IDs and validation; it changes RGB only and preserves alpha. Fade, dirt and scratches live in
foreground-local coordinates, scaled relative to the pad rather than raw raster resolution. Preserve
pristine artwork. Mild/moderate/forced examples are uncalibrated engineering settings.

One independent scene-lighting stream samples a constant/linear low-frequency illumination field
and restrained tint in scene coordinates. Apply common modulation in linear RGB after surface
composition and before final capture effects; the background texture affine does not move lighting.
This is a shared qualitative approximation, not physical sun-angle/material shading. Photographs
remain allowed with declared/unknown baked-lighting assumptions; modulation cannot remove baked
shadows. New examples avoid independent light/shadow stacks; legacy profiles remain selectable.

Pads are planar mats/markings without modeled height. No decorative drop shadows, normal/roughness
response, specular shading or cast-shadow simulation is included.

Procedural grass-like strips/blades and irregular debris-like polygons are bounded unlabeled
scene-plane layers, projected through the same homography. Their independent stream and geometry
participate in the scene plan. No imported occluder catalog role is added. They composite before
shared lighting and final capture effects; they are geometry fixtures, not validated vegetation.

- Full coverage is projected target alpha before later occlusion; visible coverage is its final contribution.
- Measure visible support as thresholded visible/full support **within the image**, distinct from the
  historical frame-clipping bbox ratio. The experimental starter floor is configurable, initially 25%.
- Drop targets below that floor with typed rejections; retain survivor IDs and derive boxes from final masks.
- Remove fully hidden annotations and their mask archive entries. Fix the existing empty-visible-mask path.
- Reject accidental empty positive candidates. Recheck require-count after occlusion; best-effort may
  keep survivors. Intentional negatives retain their sampled meaning.
- Keep appearance-only study invariants strict. Occlusion comparisons explicitly expect annotation changes.

Keep pool schema v2 with additive bounded scene evidence. Add a renderer-semantics identity to contract
and run records: upgrades require **fresh runs**, old pools remain inspectable/exportable, and resume
within the new semantics remains supported. Include enabled settings in cost identity, preflight
confidence, memory estimates and exclusive timings.

## Verification

Evaluation fixtures cover perfect/missing/duplicate/wrong-class/negative/empty/crowd predictions;
malformed geometry and masks; coverage/identity failures; exact masks and polygon loss; optional
metadata and lineage hash mismatch; compatible comparison and canonical backend parity.

Projection fixtures use known synthetic cameras and invalid/unit/behind-camera cases. Renderer checks
cover field continuity/orientation, linear RGB, source-resolution-independent wear, alpha, partial/full
and overlapping occlusion, frame clipping, threshold boundaries, count policy, negatives, exact masks,
exports, serial/process behavior, resume boundaries and bounded resources.

Run Python 3.13/3.14, schema/package checks, appropriate Windows and ci:full journeys. Ensure base CLI
imports without the evaluation extra; CI scoring tests install it. Validate report links and inspect
images. Raw results remain ignored; only compact reviewed summaries and selected sheets are tracked.

Initial paired screens use two warmups and twenty measured fixtures per treatment plus forced rare
coverage. Final production comparison uses three rotating-order repetitions, twenty accepted measured
outputs plus two warmups per cell, corrected artwork, and no competing performance runs. Report retries,
QA/mask/writing costs, accepted throughput, memory and host/sample limits; no universal timing gate.

## Future use and explicit deferrals

- #59: external real labels/predictions and controlled repeated training remain future inputs; this round
  supplies scoring, provenance and failure inspection, not an accuracy claim or a training dependency.
- #61: actual deployment calibration requires captures and measurements; audit/project tools specify and
  validate those inputs without inventing unknown camera parameters or fitting from image proxies.
- #62: aligned PBR maps, material/normal/view conventions and physical lighting remain later decisions.
- #63 / #31: raised/non-planar targets, imported occluders and nested relationships remain separate work.
- #64: prepare matched evaluation/condition identities and annotation fixtures; defer Blender installation,
  GPU setup and runtime. Future experiments compare equal dataset size and generation-time budgets,
  distinguish textured planes from physical scenes, account for baked illumination, and include cold
  startup, scene reuse, annotation/QA/output and asset-preparation costs. No cross-engine pixel equality.

Do not close an issue whose remaining real-data or physical-model acceptance is unfulfilled. Update it
with completed round-one items and explicit prerequisites for the next planning round.
