# Camera, ground and environment round

This round implements the decisions from the camera and background planning interview on top of the
surface-integration work. It remains an engineering study: visual plausibility is not evidence of
real-image accuracy or detector improvement. See #28 and #59–#64 for the broader unfinished goals.

## Scope and contracts

- Provide an explicit, saved drone-camera preset. Sample yaw around the full circle, independently of
  a bounded continuous tilt away from nadir; bias the distribution toward overhead views. Preserve
  earlier fixed-camera configurations. Reuse each sampled pose across paired treatments, preserve
  group framing, solve for reference object size within bounded distances, and record actual results.
- Offer view-relative ground texture scale, with 0.5–1.5 texture spans across the central view as the
  target, and retain fixed-metre scale. Keep PBR maps registered and derive bounded ground coverage
  from the camera. Record when geometry, horizon, clipping or safety limits prevent the target.
- Explore optional explicit open, indoor and outdoor environments. Real room geometry, a ceiling above
  the camera and lights are required for indoor tests. Walls are scene content, not automatic scenery
  to cover the horizon. Promote only after visibility, annotation and paired visual checks.
- Test opt-in linear-light composition for both foregrounds and procedural occluders, retaining the
  legacy output and shared shade option. Alpha, geometric masks, scene randomness, resume and old
  identity contracts remain intact. A negative visual verdict is a valid outcome.
- Support locally usable materials with documented terms and attribution, preserving source and
  license details and avoiding redistribution of assets without recorded permission. Asset selection
  is not restricted to two examples, and unknown permission is not inferred.
- Add local-testable per-completed-cell archive and verified retrieval. Compression and transfer occur
  between timed cells. CLI/session adapters are configurable; credentials are never embedded. No
  Colab session is started in this round.
- Audit below-floor occlusion and sharp-mask versus RGB behavior; do not change visibility acceptance
  or imply that polygons reproduce arbitrary RLE topology.

## Evidence and limits

Screen all cue families before spending remaining time on refinements; allow up to two adjustment
rounds per family and independent visual review. Final synthetic layouts must be separate from those
used during development. Use guarded 640-square CPU previews and limited 1280-square quality checks
when feasible. Keep measured warmups, retries, setup, render/export, resource use, failures and actual
configuration distinguishable. Validate geometry and annotations exactly, review image differences
visually and report ordinary repeat variability. Paired local 640-square optimization trials target
three alternating repeats with two warmups and four measured images per cell, but incomplete studies
remain exploratory. Do not alter quality settings to manufacture speed gains or generalize a hardware
profile from one machine.

The local execution budget is four hours from 2026-10-27 22:33:42 UTC, with the last hour reserved for
verification. Shared 640-square speed experiments have a 30-minute allowance, plus at most 15 minutes
for 2D. Stop or reduce work on memory/swap safety signals; never weaken guards after a stop. Keep raw
assets and generation results in ignored output directories; retain a compact reproducible report and
selected review images. Reports must distinguish planned, completed and untested cells.

## Explicitly deferred

Real-reference collection and calibration, trained-model comparisons, general Blender integration into
the product, a core Blender backend, wet-weather simulation, imported mesh context, changing existing
visibility thresholds, and broad physical 2D reflectance/contact-shadow modeling remain future work.
The Blender/2D comparison still needs matched training budgets and independent real evaluation before
claiming a downstream benefit (#59/#61/#64). Hardware-class performance baselines remain open (#28).

## Visibility and annotation audit

The 2D renderer composites targets before evaluating procedural occlusion. With best-effort count
policy, a target whose visible support falls below the configured floor may be omitted from the
annotations while a visible fragment remains in RGB; if no target remains, the candidate is rejected.
Require-count instead rejects an incomplete candidate. The Blender pilot retries a partially visible
target below 25% support up to eight attempts; it also rejects accidental empty positive scenes. Its
labels use sharp frame-zero geometry even when beauty RGB uses camera blur or depth of field. These
policies are different and unchanged. COCO RLE retains mask topology; YOLO polygon conversion has
known fidelity limits and cannot represent every mask hole exactly.

## Current evidence limit

The 2D screen compared eight paired fixtures and 24 rendered images; geometry, full and visible
masks and annotations matched across treatments. Independent crop review found no clear broad
realism win, so linear compositing and shared shade stay opt-in. An early local Blender smoke produced
one accepted image each for open, indoor and outdoor with the same camera and target. This was an
earlier plain-wall prototype, not a qualification of the current configurable environment.

The wider screen stopped after two completed images when the system-wide swap-out guard rose by
46,096,384 bytes; a later reduced one-worker, one-image attempt stopped at the same unchanged guard
after 41,795,584 bytes. The available-memory and process-RSS measures were not the limiting guard.
No further rendering or timing was attempted in this session. Runtime testing of the final motion,
distortion and textured-wall changes, held-out visual review, 2D/3D timing confirmation and 1280px
quality remain incomplete. See the report for evidence and reproduction commands.


A single guarded retry at 22:56 UTC on 2026-10-27 also stopped during Blender startup: the monitored
process tree peaked at 974,893,056 bytes RSS, minimum available system memory was 9,781,575,680 bytes,
and system-wide swap-out increased by 49,864,704 bytes. No image completed; subsequent rendering and
timing were not attempted. Swap is host-wide, so this signal does not attribute those writes to Blender.
