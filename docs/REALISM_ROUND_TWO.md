# Realism and throughput round two

Approved after the 2026-10-26 planning interview. This is the implementation agreement; delivery
checkboxes remain open until the corresponding evidence and review are complete.

## Independent deliveries

- [x] Opt-in `scene.foreground_resampling: premultiplied`; legacy remains default. Preserve geometry,
  integer alpha, annotations, omitted-mode identity and historical resume. Correct resize, rotation and
  perspective filtering; encoded-RGB composition and new physical 2D effects stay outside this change.
- [x] Bounded rolling scheduling with deterministic slot/retry/commit order, coordinator ownership,
  control/resume and submitted-but-uncommitted memory bounds. Promote only after exact-output checks,
  at least5% median gain on the repeated four-worker heavy study, no lighter two-worker regression
  above5%, and no same-cap peak-RAM increase above15%. Otherwise retain the prototype/verdict.
- [x] Reusable optional BlenderProc harness, separate from core generation and its planar pool. Pin
  BlenderProc2.8.0 / Blender4.2.1; use CPU initially. Required COCO RGB, visible/full geometric masks,
  boxes and provenance must feed the existing evaluator. A native Blender pool/backend is deferred.

## Physical pilot and annotation policy

The square pad is approximately1m; configure square1×1m, rectangle1×0.75m and thickness3mm as nominal
assumptions. Preserve corrected artwork/aspect. Panels are rigid, flat and locally supported without
conforming to terrain, interpenetrating it or floating conspicuously.

Acquire a small CC0 set: three PBR grounds and two HDR environments, with source/licence/hash records.
Test opaque plastic roughness.25/.5/.8, normal strength, UV scale/orientation, coherent daylight,
overcast/shade, single/mixed artificial night lights and environmental shadow casters. Cover camera
intrinsics/pose, aperture/focus, distortion, camera-trajectory/shutter blur, uncalibrated exposure/tone/
sensor-noise controls and bounded light haze. Wet weather, complex environments and detailed sensors
are deferred. Match measured projected target/count/viewpoint support from a pinned2D reference;
include closeups. Normalized2D transforms are not physical-camera measurements.

Use sharp geometry at the reference camera pose for labels, regardless of blurred RGB. Implement
isolated full and occlusion-aware visible masks, consistently distorted and clipped before boxes.
Resample controlled-study scenes with any0<visible/full in-frame support<25%; count incurred rejected
costs. Fully hidden annotations disappear, accidental empty positives are rejected, intentional
negatives remain explicit. Do not change normal2D acceptance policy.

COCO/RLE is canonical. Attempt YOLO detection/segmentation once, allowing one focused repair pass.
Bound conversion complexity/time, report topology and serialized polygon fidelity, and never publish
partly labeled images as complete. Failed optional formats get an unavailable/failure manifest.

## Evidence, safety and delivery

Alpha: paired production-renderer fixtures, hidden-transparent-RGB tests, all maintained families,
generic RGBA, exact alpha/mask/annotation checks, contract/resume compatibility and measured costs.
Scheduler: skew/retry/failure/bound/control tests, external stop/resume, three rotating48+2 heavy
repetitions per arm and repeated light controls. Keep old source pinned and separate identities.

Blender: diagnostic renders first, then approximately2h study rendering; prioritize paired feature
coverage over a large throughput matrix. Fast/high-quality settings begin at32/128 samples. Separate
cold setup, reused-scene render, annotation/rejection/encoding/export costs. Sparse timings are
exploratory. No model-benefit, calibrated-realism, cross-host speed or engine-ratio claim is implied.

Guard studies at2GiB available RAM,10GiB summed process-tree RSS and16MiB additional host swap-out;
do not lower safeguards after a stop. Review images autonomously and present results at the end.
Use separate reviewable PRs, resolve review findings, pass affected tests/schema/package/fullCLI/platform
checks, then merge accepted changes. Keep raw outputs/assets ignored and compact evidence reviewed.

Future use: #59 real transfer/model experiments; #61 capture/scale calibration; #62 alpha/material/
lighting follow-ups; #63 contact/environmental occlusion; #64 matched-engine pilot; #28 hardware-class
baselines. Real references and training remain later inputs. The pilot informs which physical cues
are worth approximating in later2D work; it does not close those broader issues.

Delivery evidence: [alpha](experiments/alpha-resampling-v1/README.md), [rolling scheduler](experiments/rolling-scheduler-v1/README.md), and [physical pilot](experiments/blender-pilot-v1/README.md). Broader issue requirements remain open.
