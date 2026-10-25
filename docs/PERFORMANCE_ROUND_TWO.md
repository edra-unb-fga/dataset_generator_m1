# Bounded performance round two

Authorized on 2026-10-25 after round-one realism evidence showed background synthesis dominating total generation time.

## Scope

Measure dominant background operations and existing decoded-cache, native-thread, worker and queue controls at intended resolution. Begin with short isolated screens, then use at least20 measured fixtures and three rotating-order production repetitions for selected comparisons. Preserve generated pixels, asset/source distributions, RNG progression, QA decisions, geometry, annotations and exact masks. Keep defaults unchanged. Raw pools/profiles/profiling traces remain ignored; retain compact reviewed evidence and reproducible drivers.

Implement only bounded improvements supported by paired measurements. Verify numerical/output equivalence against the immutable baseline before accepting a speedup. Do not trade quality/diversity for throughput silently. Distinguish warmup, preparation, generation, accepted yield and full command time; disclose host memory/load and sample limits. CI checks correctness, not latency. Hardware-class recommendations remain blocked on additional-machine evidence (#28).

## Decision boundary

Stop for a focused planning session if the next useful step changes image fidelity, source/recipe distributions, annotation semantics or requires substantial architecture. Physical effects, calibrated capture distributions, richer occluders, real-model training/inference and Blender runtime remain deferred. Missing real-reference/evaluation inputs remain explicit; performance evidence is not model-accuracy evidence.

## Working sequence

1. Pin baseline, record environment, profile recipes with QA intact and identify exclusive hotspots.
2. Test one candidate optimization at a time with unchanged inputs and equality checks.
3. Measure existing execution controls separately; retain local policies without changing generic defaults.
4. Validate selected improvements through production, masks/exports, resume and maintained-family checks; review and deliver via PRs with full CI/Windows where affected.
5. Record rejected candidates, remaining bottlenecks and the precise next planning decision.

## Completion and next decision

Delivered through PR #70. The [retained evidence](experiments/background-performance-v1/README.md)
contains the measured source commits, software, reproducible drivers, per-repeat throughput/resources,
exclusive recipe operation evidence, exact-output checks and visual report. Defaults remain unchanged.
The changes remove redundant copies, release DAG values after final use, stream exact multiband
arithmetic and reuse identical full/visible mask polygonization. A separate cost revision prevents
old timing observations from calibrating the new implementation while preserving generation identity.

The final production A/B uses3 rotating-order repetitions of20 accepted images (+2 warmups),1280²,
the shipped heavy appearance/standard mixture, three execution policies and four QA outputs per pool.
Every case matches encoded images and geometry/annotation/mask signatures. Recipe pairs also match
QA/warnings, lineage, parameters, graph hash and RNG state. Same-contract stop/resume preserves
committed image hashes. Full deterministic/platform/maintained-family checks accompany delivery.

The decoded cache was not promoted; queue/thread combinations from the short screen were not stable
enough to recommend. Generic resource estimates were not fitted to this host. Multi-machine baseline
collection remains #28. Large Gaussian smoothing dominates remaining synthesis work. The next
implementation decision requires either an explicit smoothing approximation/fidelity budget or a
bounded scheduling/transport design covering memory, determinism, retry/commit ordering and run
control. Synthesized-background caching also requires a separate diversity/RNG policy. These are
outside this round; #59/#61–64 still retain real-model, capture, physical-effects and Blender work.
