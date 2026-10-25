# Worker/thread scaling and conservative RAM planning

Authorized follow-up to the background performance round: test high worker/native-thread combinations,
including six workers with24 OpenCV threads each, under the same generation contract. The requested
12 GiB ceiling is not permission to consume unavailable host memory. The study ramps up under a lower
sampled RSS guard, an available-memory floor, a swap-out guard and a per-cell timeout. These are
experimental watchdogs, not hard OS memory limits; raw partial evidence is retained after an abort.

## Scope

- Compare six workers with1/4/24 native threads, and roughly24-native-thread configurations split
  across1/2/4 workers. Native threads are per worker and control OpenCV only.
- Use immutable renderer source, identical encoded pixels and annotation/mask signatures, repeated
  intended-resolution production, and rotating order. Record process-tree RSS and thread counts,
  preparation/warmup-inclusive command observations separately from generation-only telemetry.
- Correct automatic RAM selection to include the complete queue/process/workspace/cache estimate.
  Reserve process/native runtime, decoded source size, cover-resize expansion, graph outputs/scratch,
  instance masks, queued serialization/receipt and25% headroom. Expose the estimate's components/version.
- Test source-header invalidation, queue capacity, impossible minimum budgets, explicit oversubscription,
  watchdog cleanup and exact generation invariants. Preserve all rendering/profile defaults and content.

## Interpretation and boundary

This is conservative shape accounting with explicit heuristic runtime/scratch reserves, not an RSS
predictor fitted to one host. It should exceed the observed workloads used for validation; no finite
heuristic guarantees memory for every native-library/effect/source combination. Sampling can miss
spikes. Summed RSS counts shared pages repeatedly and is intentionally conservative for the watchdog.
Generic hardware-class recommendations still require #28. The richer estimate may select fewer
workers under `auto`; explicit workers remain unchanged and over-budget plans are warned about.

The study does not change scheduling, native libraries, foreground effects, QA, source distributions,
mask/annotation semantics, defaults, or cache policy. Approximate smoothing and a rolling scheduler
remain future planning decisions. Read `PERFORMANCE_ROUND_TWO.md` and the retained scaling report for
background and measured results.
