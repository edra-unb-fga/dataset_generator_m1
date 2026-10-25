# Dataset Generator M1 Roadmap

The normative current behavior lives in `docs/SPEC.md`. This file orders future work by evidence and
dependency; unchecked items are not promises that current commands already implement them.

## Now

### Practical workflow review stack

- [ ] #49 / PR #51: exclusive coordinator ownership and malformed-input safety.
- [ ] #50 / PR #53: complete diagnostics, resume telemetry and accepted-output calibration.
- [ ] #52 / PR #54: declarative rectangular-pad family, explicit count policy and family discovery.
- [ ] #33 / PR #55: pre-generation source feasibility and verified background/content isolation.
- [ ] #56 / PR #58: experimental drone screens, pinned colour materials and planar mapping.
- [ ] #57: execution budgets, isolated portable production benchmarks and local tuning guidance.

These changes are implemented in the stacked branches but remain unchecked here until review/merge.
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

## Later

- [ ] [#31](https://github.com/edra-unb-fga/dataset_generator_m1/issues/31): implement reviewed typed nested placement without changing landing/manometro controls.
- [ ] Promote bounded decoded-asset caching only under measured representative reuse; synthesized-background caching remains experimental.
- [ ] Add COCO/RLE export only when real mask topology evidence justifies the additional format.
- [ ] Add family scaffolding and narrow hooks only after declarative rules prove insufficient.
- [ ] Evaluate random-phase synthesis for approved homogeneous microtextures.
- [ ] Evaluate patch quilting for structured textures after current mixer diversity is measured.

### Realism and real-image evidence

These follow-ups are proposed research, not implemented capabilities or new merge requirements for
#56 / PR #58. Preserve the retained material-lighting verdict and historical experiment evidence.

- [ ] [#59](https://github.com/edra-unb-fga/dataset_generator_m1/issues/59): evaluate external predictions on separate real and synthetic sets, with capture/session isolation, controlled training provenance, repeated seeds, uncertainty and failure slices.
- [ ] [#61](https://github.com/edra-unb-fga/dataset_generator_m1/issues/61): calibrate planar camera/physical scale and capture-effect severity from permitted real references; record unknowns and keep development references separate from final evaluation.
- [ ] [#62](https://github.com/edra-unb-fga/dataset_generator_m1/issues/62): prototype shared foreground/ground lighting using #56's retained material work, with paired visual/cost evidence and explicit physical limits.
- [ ] [#63](https://github.com/edra-unb-fga/dataset_generator_m1/issues/63): study pad wear, surface interaction and environmental occlusion; distinguish appearance-only alpha invariants from deliberate visible-mask changes and coordinate with #31 only where relationships require it.
- [ ] [#64](https://github.com/edra-unb-fga/dataset_generator_m1/issues/64): compare planar synthesis and BlenderProc using matched scene/annotation contracts, real-image accuracy, equal dataset-size/time budgets and complete generation/setup costs.

Start with real-reference requirements and #59's evaluation contract. Use bounded paired pilots before
expensive studies; missing reference data or predictions must remain explicit evidence gaps. The
BlenderProc study is a separate optional future harness, not a generator dependency or a commitment to
begin 3D implementation now. Existing defaults and production boundaries remain unchanged.

## Deferred

GUI, model training, GPU or distributed execution, multi-family generation, exact quotas,
vendor-specific telemetry, and general legacy-config migration are deliberately outside the current
product boundary.

[External model-prediction evaluation/failure analysis (#59)](https://github.com/edra-unb-fga/dataset_generator_m1/issues/59) is a later analytical track, not a generator
training dependency: preserve sample/manifests and configured versus measured conditions, compare real
evaluation separately from synthetic regression, and analyze scale, perspective, visibility, material
and camera slices without inferring training benefit from visual attractiveness.
