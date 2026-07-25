# Dataset Generator M1 Roadmap

Status reflects the version-1 implementation. Items are ordered by dependency, not calendar date.

## Delivered baseline

- [x] Clean-break strict Pydantic v2 profiles, packaged family definitions, duplicate-key-safe YAML, capability validation, and generated schema support.
- [x] Fingerprinted asset catalogs with class mapping, metadata, decode/hash validation, weighting indexes, and duplicate-quality reporting.
- [x] Deterministic scene planning, rectangular camera crop, one shared homography, transformed alpha masks, visible-mask boxes, truncation policy, intentional negatives, and typed candidate rejection.
- [x] Separate versioned background recipe catalog, conservative typed DAG, same-material default, explicit cross-material pairs, source roles/reuse, float/color-space discipline, QA, warnings, provenance, and focused preview.
- [x] Rich live/full/plain/quiet output, JSON results, stage/node timing, psutil metrics, distribution/rejection audits, configured-versus-observed mix, and QA galleries.
- [x] Atomic generation pools, fingerprint-validated resume, disk/runtime/rejection guards, deterministic process workers with bounded in-flight batches, benchmark, comparison, and multi-pool YOLO export.
- [x] Normative spec, domain context, concise quickstart, shipped-example/schema drift validation, and Python 3.10–3.13 CI matrix.

## Calibration and operational hardening

- [ ] Run focused Monte Carlo background previews against the production catalog; review false warnings and hard failures, then version and freeze calibrated QA thresholds.
- [ ] Establish benchmark baselines per supported hardware class and define regression budgets instead of absolute timing assertions.
- [ ] Add fault-injection tests for disk exhaustion and first/second interrupt behavior on every supported OS.
- [ ] Deepen exclusive renderer timing (decode, foreground appearance, rotation/resize, mask warp, composition, annotation, and final appearance) where profiling shows actionability.

## Measurement-gated performance work

- [ ] Tune `workers=auto` from memory, decode, IPC, and throughput evidence rather than CPU count alone.
- [ ] Add a bounded decoded-asset cache only if catalog decode is a demonstrated bottleneck.
- [ ] Add a bounded content-addressed synthesized-background cache only if recipe cost and reuse make it beneficial.
- [ ] Evaluate random-phase synthesis only for catalog assets explicitly classified as homogeneous microtexture.
- [ ] Evaluate patch quilting for structured textures after conservative mixer diversity and quality are measured.

## Segmentation

- [ ] Store compressed instance masks as durable pool evidence.
- [ ] Add YOLO segmentation export and mask QA galleries.
- [ ] Optionally replace bbox-area truncation/spacing with mask-area visibility and overlap policies.

## Family extensibility

- [ ] Add a family-authoring validator/scaffolder and documentation.
- [ ] Introduce narrow Python family hooks only after at least two real families require behavior that declarative family rules cannot express.

## Explicitly deferred

GUI, model training/evaluation, multi-family generation, exact sampling quotas, GPU/distributed execution, vendor-specific hardware telemetry, and legacy-config migration are not version-1 goals.
