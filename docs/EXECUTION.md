# Execution planning and portable fresh runs

Use the same composer and explicit execution overrides on different machines. Scene/content identity,
execution identity and exact-file/environment provenance are different fields in `run.json`. Moving a
checkout does not change generation identity when logical source choices/content and renderer semantics
are unchanged. Native libraries/versions may change pixels; no cross-version pixel guarantee or
cross-machine resume is promised. Resume still requires the exact original contract/catalog.

## Local tuning without machine-specific source edits

Use the [portable tuning workflow](EXECUTION_TUNING.md) to create hardware-informed candidates,
screen under guards, confirm finalists and save an evidence-bound local execution override.
Hardware capacity provides starting choices; measured throughput determines a local near-best choice.

Keep private/local composers and override files under ignored `configs/local/`. For example:

```yaml
execution:
  workers: auto
  cpu_budget: 8
  ram_budget_mb: 8192
  native_threads: 1
  max_in_flight: 8
  decoded_cache_mb: 256
```

These are **illustrative numbers, not a recommendation for this or another computer**. Preflight
reports requested/effective policy and advisory peak memory. `workers: auto` respects CPU/RAM planning
limits. Explicit workers that violate an explicit CPU budget fail; a cache larger than the RAM budget
fails. When an explicit CPU budget is set without a thread choice, OpenCV threads default to one and
that effective choice is reported. Other native libraries may still have their own thread pools.
`native_threads` controls OpenCV, not a hard OS CPU limit. OpenCV state is restored after serial runs.
Automatic workers default to one OpenCV thread each unless explicitly configured and respect CPU
affinity where available. An oversized CPU budget does not create additional automatic CPU capacity.

RAM estimates are conservative heuristics, not hard process RSS limits. Large sources, backend
temporary arrays and OS load can exceed estimates. Cache capacity and submitted-work count are actual
bounds: the total decoded-cache budget is divided between workers, LRU entries count their uint8
payload bytes, and cache hits return independent copies. Transformed images, random backgrounds and
mutable alpha arrays are never cached. The default cache is zero until a representative benchmark
shows benefit. Queue windows remain bounded batches, with deterministic ordered commits, rather than
an unreviewed rolling scheduler. `max_in_flight` must be at least the effective worker count.

The versioned `memory_estimate` breakdown reserves interpreter/native runtime per process, source
dimensions discovered from image headers, correlated cover-resize expansion, live graph arrays/operator
scratch and the maximum of synthesis/render/evidence phases. It includes foreground rotation/resize,
instance masks, coordinator QA, returned-result copies, cache payload and20% headroom. Missing source
dimensions are reported explicitly. Automatic selection checks this complete estimate for each worker
count and respects an explicit queue capacity. If even one worker cannot fit, it retains one worker
with an over-budget warning. More conservative accounting can select fewer automatic workers;
explicit worker counts stay unchanged. Native threads above detected CPU capacity produce a warning
when no explicit CPU budget forbids the request. These reserves are not a hard allocation guarantee.

Budgets never reduce masks, dimensions, appearance or count policy. Reduce worker/queue/cache settings
explicitly when warned. Slow effects remain selectable. Preflight preparation is bound to source
catalog content too; changed assets invalidate prepared generation.

## Portable production benchmark

```powershell
uv run python -m dataset_generator_m1 benchmark --production `
  --config examples/benchmarks/landing-screen.yaml `
  --execution-matrix examples/benchmarks/execution-policies.yaml `
  --samples 20 --warmup 2 --repeats 3 `
  --output-dir outputs/experiments/execution-my-machine --output-format json
```

The strict matrix changes execution only. It rotates variant order between repeats, validates every
policy before output creation, uses the production generation path, inspects each pool, and requires
equal scene/annotation/mask signatures. Warmup pools are separate from measured pools. Wall time,
accepted throughput, retries, mask/encoding/write/QA stage work and sampled resource peaks are retained.
Observations are isolated inside the ignored benchmark bundle, not mixed into production calibration.
Low sample/repeat counts are explicitly marked. The older command without `--production` remains a
render/encode/write microbenchmark and is not an accepted-output throughput measurement.

The shipped screen is deliberately 320×240 and 1–2 objects to keep iteration affordable. Repeat with
the intended production dimensions, source diversity, masks, QA and appearance before recommendations.
Run policies one at a time without competing CPU work; repeat under stated OS/software conditions.
Record sanitized `benchmark.json`, source/contract fingerprints, evidence size and limitations. Do not
commit full pools, private paths, hostnames or usernames. Reviewed generic execution bundles may be
placed in the workspace profile catalog; a local optimum is not a hardware-class recommendation.

## Still experimental

Rich may correctly refuse `start` in automation wrappers whose stdin is not a real terminal, even
when they display terminal escape sequences. Use an actual Windows Terminal/PowerShell or POSIX
terminal for the interactive journey; atomic commands remain available in non-TTY environments.

Worker setup reuse, rolling scheduling, shared-memory
transport and synthesized-background caching remain separate candidates. The bounded decoded cache
and explicit native/queue controls enable comparisons without making them universal defaults. #28
requires additional stable hardware measurements; CI correctness evidence is not a latency budget.

## Pixel-preserving implementation upgrades

A separate performance-implementation revision participates in execution identities and cost-observation fingerprints. A cost change that preserves generated pixels/geometry need not change renderer semantics or invalidate compatible pool resume, but old timing observations must not be mixed into the new implementation's ETA calibration. Existing observations remain readable; nonmatching fingerprints are excluded. Revision changes do not promote any thread/worker/cache default.

The [background performance study](experiments/background-performance-v1/README.md) records local
cache/thread/worker/queue measurements and exact-content implementation comparisons. A256 MiB decoded
cache was slower in this workload despite hits; native threading helped this particular host. Keep
these as local choices until #28 has additional-machine evidence. Observed process-tree RSS exceeded
the advisory planner estimate in this study; do not treat that estimate as a hard memory limit or
infer a safe worker count from throughput alone.

The follow-up [worker/thread scaling study](experiments/worker-scaling-v1/README.md) includes6 workers
with24 requested OpenCV threads each, under a lower host-appropriate experimental watchdog. Requested
threads are per worker; actual OS threads and other library pools differ. The portable study driver
accepts `--rss-limit-gib`, `--min-available-gib`, `--max-swap-out-mib` and
`--cell-timeout-seconds`; it retains abort evidence and stops the benchmark session/descendants.
Watchdogs sample resources and can miss spikes; normal generation RAM budgets remain advisory.

The [high-worker capacity follow-up](experiments/high-workers-v1/README.md) stopped12 workers at its
available-memory floor and skipped16/24. The phase/lifetime v3 model replaces v2's expired-array and
exclusive-phase overcounting; it remains an RSS planning upper estimate, not typical physical usage.
The driver also supports `--detailed-memory`, `--pss-limit-gib` and `--poll-interval-seconds`.
Linux PSS/USS samples distinguish proportional/private memory from summed RSS. Available host RAM and
swap growth remain independent guards; unsupported proportional-memory sampling is reported as unknown.
