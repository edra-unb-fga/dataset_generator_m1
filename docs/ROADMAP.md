# Dataset Generator M1 Roadmap

The normative current behavior lives in `docs/SPEC.md`. This file orders future work by evidence and
dependency; unchecked items are not promises that current commands already implement them.

## Reading this roadmap

The [study index](experiments/README.md) distinguishes shipped capabilities, optional experimental
work, and historical stopped or superseded results. [Scene presets](SCENE_PRESETS.md) describe
visual context independently of annotation families. Remaining real-image calibration, model-transfer
evidence and multi-hardware baselines are open; synthetic screens do not establish production readiness.

### Procedural consolidation follow-up

The optional harness now has reusable `open`, `outdoor` and `indoor` scene presets, explicit sampled
light/caster/material controls and ordinary seeded scene preparation. The
[bounded visual screen](experiments/procedural-scenes-v1/README.md) establishes execution evidence,
with source-revision limits, rather than calibrated distributions. Next priorities are:

- Bind ground/material eligibility to environment meaning; the generic presets currently accept
  every supplied ground unless `ground_weights` restricts the catalog.
- Refine indoor lamp power, emitter size and placement together, retaining glare cases deliberately
  without making washed-out targets the routine outcome.
- Review outdoor shadows and reflections with varied framing; walls may be outside top-down views,
  and sampled casters need not cast visible shadows on the target.
- Add reviewed weighted mixtures and conditional relationships only after the component presets
  are useful. Atmosphere and wear still come from template treatments, not preset-level distributions.

Continue to retain compact decisions and selected evidence through the study index, rather than
promoting one-off diagnostic fixture scripts into defaults. Independent real-data/model evaluation,
calibrated materials and representative coverage remain open under #59 and #61–#64.

## Now

### Practical workflow review stack

- [x] #49 / PR #51: exclusive coordinator ownership and malformed-input safety.
- [x] #50 / PR #53: complete diagnostics, resume telemetry and accepted-output calibration.
- [x] #52 / PR #54: declarative rectangular-pad family, explicit count policy and family discovery.
- [x] #33 / PR #55: pre-generation source feasibility and verified background/content isolation.
- [x] #56 / PR #58: experimental drone screens, pinned colour materials and planar mapping.
- [x] #57 / PR #60: execution budgets, isolated portable production benchmarks and local tuning guidance.

These changes were reviewed, repaired and merged in dependency order on 2026-10-24.
Read docs/PRACTICAL_WORKFLOW.md for acceptance scope. The historical checklist below records earlier
deliveries; the follow-ups above repair acceptance gaps rather than rewriting their historical reports.

- [x] Complete architecture integration and keep schemas, examples, CLI, and generated artifacts aligned.
- [x] Run the controlled heavy-augmentation study for both families and review visual/cost attribution.
- [x] Adopt lean PR, issue, experiment, and Windows correctness workflows without release bureaucracy.
- [x] [#11](https://github.com/edra-unb-fga/dataset_generator_m1/issues/11): deliver schema-v2 composers, typed inline values, reusable profile catalogs, and deterministic override precedence.
- [x] [#12](https://github.com/edra-unb-fga/dataset_generator_m1/issues/12): preserve native and patch-based fog plus realistic, fast, legacy, diagnostic, and stress appearance profiles.
- [x] [#13](https://github.com/edra-unb-fga/dataset_generator_m1/issues/13): deliver performance-aware preflight, local probes, bound warning receipts, and active-time ETA.
- [x] [#14](https://github.com/edra-unb-fga/dataset_generator_m1/issues/14): deliver durable pause/continue/stop/resume control with atomic state and an auditable event log.
- [x] [#15](https://github.com/edra-unb-fga/dataset_generator_m1/issues/15): deliver the guided Rich configuration cockpit, complete effect guidance, and explicit profile promotion.
- [x] [#17](https://github.com/edra-unb-fga/dataset_generator_m1/issues/17): support Python 3.13/3.14 with required fast CI and opt-in full CLI validation.
- [x] [#18](https://github.com/edra-unb-fga/dataset_generator_m1/issues/18): share preparation, calibrate from sanitized production runs, and inspect pool integrity.
- [x] [#19](https://github.com/edra-unb-fga/dataset_generator_m1/issues/19): guide one interactive journey from discovery through persistent results.
- [x] [#23](https://github.com/edra-unb-fga/dataset_generator_m1/issues/23): retain pool-v2 full/visible mask evidence and export measured YOLO instance segmentation.
- [x] [#36](https://github.com/edra-unb-fga/dataset_generator_m1/issues/36): retain complete placement diagnostics before any placement-policy tuning.
- [x] [#37](https://github.com/edra-unb-fga/dataset_generator_m1/issues/37): use content hashes for strict asset-disjoint identity.
- [x] [#38](https://github.com/edra-unb-fga/dataset_generator_m1/issues/38): harden coordinator-owned telemetry polling and monitor shutdown.
- [x] [#39](https://github.com/edra-unb-fga/dataset_generator_m1/issues/39): estimate completion from accepted-output throughput and handle malformed local observations safely.
- [x] [#40](https://github.com/edra-unb-fga/dataset_generator_m1/issues/40): harden composer resolution, guided-start tests, and pool-path inspection.

## Next

- [x] [#3](https://github.com/edra-unb-fga/dataset_generator_m1/issues/3): diagnose landing placement and visibility rejections with spatial and object-level evidence.
- [x] [#24](https://github.com/edra-unb-fga/dataset_generator_m1/issues/24): select the family-declared `typed-mixed` nested-placement model through a retained prototype.
- [x] [#4](https://github.com/edra-unb-fga/dataset_generator_m1/issues/4): measure and expose asset-disjoint split feasibility without changing hash assignment policy. The infeasible reviewed pools motivate [#33](https://github.com/edra-unb-fga/dataset_generator_m1/issues/33), a separate pre-generation source/catalog partitioning study.
- [x] [#6](https://github.com/edra-unb-fga/dataset_generator_m1/issues/6): continuously sample the coordinator, workers, and descendants with bounded auditable telemetry and an explicit opt-out.
- [ ] [#29](https://github.com/edra-unb-fga/dataset_generator_m1/issues/29): improve landing requested-count fulfillment using complete placement evidence without silent policy drift.
- [ ] [#27](https://github.com/edra-unb-fga/dataset_generator_m1/issues/27): calibrate background QA warnings and hard failures after complete placement diagnostics.
- [ ] [#28](https://github.com/edra-unb-fga/dataset_generator_m1/issues/28): establish reviewed benchmark baselines by hardware class using hardened continuous process-tree evidence; no universal timing budget exists yet.
  The portable [execution tuning workflow](EXECUTION_TUNING.md) now generates capacity candidates and
  repeated-evidence local overrides; the [3–6 worker study](experiments/execution-tuning-v1/README.md)
  supplies one-host evidence. Additional hardware classes remain required.

The bounded [background performance round](PERFORMANCE_ROUND_TWO.md) removes redundant work with
exact-output production evidence and unchanged defaults. Its [local report](experiments/background-performance-v1/README.md)
does not complete #28. The [bounded rolling scheduler](experiments/rolling-scheduler-v1/README.md) now removes batch barriers with exact-output evidence. Further gains require a scoped smoothing/fidelity or transport
decision; preserve deterministic commits, bounded memory, stop/resume and any explicit diversity policy.

## Later

- [ ] [#31](https://github.com/edra-unb-fga/dataset_generator_m1/issues/31): implement reviewed typed nested placement without changing landing/manometro controls.
- [ ] Promote bounded decoded-asset caching only under measured representative reuse; synthesized-background caching remains experimental.
- [ ] Add COCO/RLE export only when real mask topology evidence justifies the additional format.
- [ ] Add family scaffolding and narrow hooks only after declarative rules prove insufficient.
- [ ] Evaluate random-phase synthesis for approved homogeneous microtextures.
- [ ] Evaluate patch quilting for structured textures after current mixer diversity is measured.

### Realism and real-image evidence

Round one delivered offline evaluation/reference foundations (#66), shared 2D illumination and wear (#67),
and procedural occlusion/final-mask acceptance (#68). See `REALISM_ROUND_ONE.md` and
`experiments/planar-surfaces-v1/README.md`. Broader real/physical acceptance below remains open; it does
not expand the historical #56 / PR #58 delivery. Preserve the retained material-lighting verdict and historical experiment evidence.

- [ ] [#59](https://github.com/edra-unb-fga/dataset_generator_m1/issues/59): evaluate external predictions on separate real and synthetic sets, with capture/session isolation, controlled training provenance, repeated seeds, uncertainty and failure slices.
- [ ] [#61](https://github.com/edra-unb-fga/dataset_generator_m1/issues/61): calibrate planar camera/physical scale and capture-effect severity from permitted real references; record unknowns and keep development references separate from final evaluation.
- [ ] [#62](https://github.com/edra-unb-fga/dataset_generator_m1/issues/62): extend the shipped qualitative shared field only with reference-supported physical/material evidence; retain the independent material prototype verdict and measured costs.
- [ ] [#63](https://github.com/edra-unb-fga/dataset_generator_m1/issues/63): study pad wear, surface interaction and environmental occlusion; distinguish appearance-only alpha invariants from deliberate visible-mask changes and coordinate with #31 only where relationships require it.
- [ ] [#64](https://github.com/edra-unb-fga/dataset_generator_m1/issues/64): compare planar synthesis and BlenderProc using matched scene/annotation contracts, real-image accuracy, equal dataset-size/time budgets and complete generation/setup costs.

Use #59's evaluation contract and keep real-reference requirements explicit; nominal engineering pilots can proceed before real captures. Use bounded paired pilots before
expensive studies; missing reference data or predictions must remain explicit evidence gaps. The separate optional [BlenderProc harness](../experiments/blenderproc/README.md) now supports nominal
physical day/night engineering studies and canonical COCO/evaluator output. Its [pilot report](experiments/blender-pilot-v1/README.md)
keeps calibration, model transfer, matched training budgets and richer environments open. Blender is
not a generator dependency or a core backend. Existing production defaults remain unchanged.

## Deferred

GUI, model training, GPU or distributed execution of the core planar generator, multi-family generation, exact quotas,
vendor-specific telemetry, and general legacy-config migration are deliberately outside the current
product boundary.

[External model-prediction evaluation/failure analysis (#59)](https://github.com/edra-unb-fga/dataset_generator_m1/issues/59) now has an offline scorer; real-data transfer and controlled external training remain future evidence, without a generator training dependency: preserve sample/manifests and configured versus measured conditions, compare real
evaluation separately from synthetic regression, and analyze scale, perspective, visibility, material
and camera slices without inferring training benefit from visual attractiveness.


The optional BlenderProc follow-up consolidates CPU/Colab GPU execution into saved, capability-selected
policies and verified portable input bundles. Native GPU OIDN removes the observed CPU-denoising
bottleneck. The separately recorded initialization study controls its renderer-session optimization;
see `experiments/blender-execution-v1/README.md`. This is engineering execution evidence, not completion
of #28/#64. The next planning session can concentrate on representative material/lighting/camera
conditions and eventual real-image/model evidence; major renderer/annotation redesign remains separate.


The [surface integration round](REALISM_ROUND_THREE.md) adds shared deterministic RGB/data wear maps,
independent material/UV/light controls in the optional harness, and an opt-in shared 2D environmental
shade candidate. The [round report](experiments/surface-integration-v1/README.md) records paired
coverage, native crops, measured costs and explicit negative/limited verdicts. Production defaults
remain unchanged. General caster recipes, calibrated material/camera response, richer scene geometry
and real detector evidence remain planning work under #62/#63/#64 and #59/#61. The isolated context
prototype branch is evidence for that discussion, not a promoted mesh-import backend. #28 remains a
multi-hardware performance requirement.


The [camera and environment round](REALISM_ROUND_FOUR.md) introduces opt-in drone tilt/ground
controls, a prototype for explicitly configured rooms and outdoor walls, experimental linear-light
2D compositing and verified cell handoff. The [initial round evidence](experiments/camera-environments-v1/README.md) is partial because host
swap-out guards stopped the local runs. The later [L4 completion report](experiments/l4-camera-completion-v1/README.md)
records the completed camera cells, annotation checks, visual review and limited speed comparisons;
see [round four](REALISM_ROUND_FOUR.md) for the full scope and limitations. The tested walls and
lighting remain visibly artificial, so environment geometry stays experimental and production defaults
remain unchanged. Real-image, model-transfer and multi-hardware requirements remain open.


The [round-five integration](REALISM_ROUND_FIVE.md) adds conservative target-placement
contracts and an experimental local foreground-context treatment. Human-reviewed synthetic
studies remain engineering evidence; real calibration, independent evaluation, physically
grounded lighting and material work under #59, #61–#64 remain open.
