# Execution planning and portable fresh runs

Use the same composer and explicit execution overrides on different machines. Scene/content identity,
execution identity and exact-file/environment provenance are different fields in `run.json`. Moving a
checkout does not change generation identity when logical source choices/content and renderer semantics
are unchanged. Native libraries/versions may change pixels; no cross-version pixel guarantee or
cross-machine resume is promised. Resume still requires the exact original contract/catalog.

## Local tuning without machine-specific source edits

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

RAM estimates are conservative heuristics, not hard process RSS limits. Large sources, backend
temporary arrays and OS load can exceed estimates. Cache capacity and submitted-work count are actual
bounds: the total decoded-cache budget is divided between workers, LRU entries count their uint8
payload bytes, and cache hits return independent copies. Transformed images, random backgrounds and
mutable alpha arrays are never cached. The default cache is zero until a representative benchmark
shows benefit. Queue windows remain bounded batches, with deterministic ordered commits, rather than
an unreviewed rolling scheduler. `max_in_flight` must be at least the effective worker count.

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

Worker setup reuse, duplicate full/visible polygonization avoidance, rolling scheduling, shared-memory
transport and synthesized-background caching remain separate candidates. The bounded decoded cache
and explicit native/queue controls enable comparisons without making them universal defaults. #28
requires additional stable hardware measurements; CI correctness evidence is not a latency budget.
