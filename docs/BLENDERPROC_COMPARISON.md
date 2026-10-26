# Planar / BlenderProc comparison

The optional source-checkout harness in `experiments/blenderproc/README.md` now supplies a bounded
engineering pilot for #64. It is separate from the core generator, uses nominal physical parameters,
and exports COCO to the existing evaluator. See `experiments/blender-pilot-v1/README.md` for the
controlled day/night material, camera, annotation and cost evidence. Real-image accuracy and physical
calibration remain unknown. This document retains the protocol for the later transfer study.

## Arms and controlled inputs

1. Existing planar profiles: pristine, current-fast/heavy, restrained camera, shared field/wear, and occlusion as separate ablations.
2. BlenderProc textured target/ground planes using the same approved artwork/source revisions. Photograph textures retain baked illumination; two textured planes do not reconstruct real geometry.
3. Additional geometry/PBR/occluders only when reference failures justify them. Attribute gains from geometry and asset complexity separately from engine choice.

Freeze the task/classes, source hashes/derivative groups, dimensions, count/negative distributions, target pixel-size/viewpoint quantiles, illumination scenarios and visibility/box policies. Shared abstract intent/quantiles are useful; equal random seeds and equal pixels across engines are not a correctness contract. Keep synthetic source partitions and real session/location holdouts distinct.

Current generation camera settings are normalized affine/projective sampling, not a calibrated physical camera. A physical arm requires measured/configured intrinsics, pose, metric target dimensions and texture scale. `reference project` checks supplied inputs against a centered world-Z=0 plane in OpenCV coordinates; it does not fit parameters or implement physical generation. Declare unknowns. For engineering pilots, explicitly configure nominal physical distributions and measure achieved support. Acquire the reference/development inputs listed in `docs/EVALUATION.md` before calling those distributions representative of deployment.

## Annotation bridge

Use canonical clipping and half-open boxes, full versus visible instance masks, stable class mapping and the declared in-frame visible-support floor. Test opaque/partial/full occlusion, overlapping targets, frame edges, holes/disconnected masks, intentional negatives and accidental empty positives. Pixel thresholds must be declared if antialiasing differs. Dirt is RGB appearance unless deliberately modeled as an occluder. Occluders are unlabeled. State whether below-floor target fragments remain unlabeled; do not compare incompatible policies as model gains.

Prepare COCO boxes/RLE masks or the repository pool/export adapter with explicit dataset role/domain and provenance. The evaluator consumes external predictions with a complete processed-image manifest, dataset digest and model/checkpoint/training metadata. Exact pool masks are primary; YOLO polygon fidelity is separate. Raised/non-planar physical geometry needs its own annotation validation, rather than being forced into the shared planar homography invariant.

## Performance and accuracy decision

For a promotion-grade performance comparison, begin with 2 warmups +20 measured accepted images and 3 rotating-order repetitions per selected arm. The bounded engineering pilot instead prioritizes three-scene paired feature coverage and records its sparse timing limitations; it does not establish a universal engine multiplier. Record cold startup, loading/material compilation, warm rendering and scene reuse, retries, masks/annotations, QA, encoding/writing and export separately. Report full accepted throughput and quality settings: engine/version, CPU/GPU, resolution, samples/adaptive threshold, denoising/bounces/motion/volume settings, CPU/RAM/VRAM where observed, and unavailable quantities. Include asset acquisition/modeling/calibration effort. No guaranteed slowdown multiplier is justified before a local pilot.

Run equal accepted-dataset-size and equal generation-time arms. Keep external training exposure, optimization/fine-tuning allocation and checkpoints fixed, or disclose differences. Use development data to choose treatments, then a separate real holdout, repeated training seeds and uncertainty respecting capture-session clustering. Report class/target-size/viewpoint/lighting/occlusion support, AP/AR, negative-scene false positives and failure crops. Synthetic oracle tests verify the scorer, not detector benefit.

Declare task-specific acceptance/cost limits before seeing holdout outcomes. Select the simplest pipeline meeting those requirements. If labels, predictions, physical measurements or requirements are absent, keep the decision pending and publish only the verified pilot and precise missing inputs. #59 owns scoring/transfer, #61 calibration, #62/#63 physical/material/geometry improvements, and #28 hardware-class generalization.
