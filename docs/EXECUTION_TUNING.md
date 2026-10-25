# Choosing execution settings on a new computer

CPU count and RAM capacity tell us which configurations to consider. They do not tell us which
configuration will generate accepted images fastest. Background mix, source dimensions, memory
bandwidth, native libraries and the bounded-batch commit schedule all affect scaling. Keep a
conservative starting policy separate from a measured local recommendation.

The shipped profile keeps one worker. `workers: auto` chooses capacity from the complete RAM estimate,
CPU budget and queue limit; it uses one OpenCV thread per worker unless explicitly configured. CPU
affinity limits are respected where supported. An explicit CPU budget can express a smaller VM or
container allocation; detected affinity is not a hard CPU-time quota. Other native libraries may own
additional threads. Generic defaults are not promoted from one machine's fastest measurement.

## 1. Prepare representative candidates

```sh
uv run python -m dataset_generator_m1 execution candidates \
  --config configs/local/my-production.yaml \
  --output-dir outputs/tuning/candidates
```

This writes `result.json`, `starting-overrides.yaml` and `matrix.yaml`. It uses usable logical CPUs
minus one (minimum one), the composer's explicit CPU/RAM budgets when provided, otherwise a planning
budget of 60% of currently available RAM. The default matrix contains a small worker-count ladder
and one/two OpenCV threads where the advisory capacity estimate fits. Cache starts at zero; each
trial uses an in-flight window equal to its worker count. Review the starting plan and exclusions.

For a deliberate local exploration, specify counts, for example `--workers 3 4 5 6 --native-threads 1 2`.
Explicit trials can exceed the conservative RAM forecast; their warnings remain visible. They are
not automatically launched or claimed safe. Use `--cpu-budget`, `--ram-budget-mb` and `--max-workers`
to express limits. Never infer free RAM from total installed capacity or from an advisory budget.

Use the intended production composer: source assets, dimensions, masks, background mix, appearance,
object counts and QA. A small-resolution screen answers a different question. Keep private assets
and machine choices under ignored `configs/local/`. Pin a clean measured checkout with the intended
performance implementation; avoid competing CPU work while measuring.

## 2. Screen under memory guards, then confirm

```sh
PYTHONPATH=src uv run python scripts/study_execution_controls.py \
  --source-root . --config configs/local/my-production.yaml \
  --matrix outputs/tuning/candidates/matrix.yaml \
  --samples 24 --warmups 2 --repeats 1 \
  --min-available-gib 2 --max-swap-out-mib 16 --rss-limit-gib 8 \
  --cell-timeout-seconds 240 --poll-interval-seconds .1 --detailed-memory \
  --output-dir outputs/tuning/screen
```

The numbers above are illustrative guard values, not a portable safe-RAM promise. Inspect current
available RAM, swap occupancy and other applications first. Choose a reserve that keeps the session
responsive; a nearly full swap calls for more caution. The host-memory floor and additional swap-out
limit protect independently of summed RSS. PSS/USS, where supported, help interpret shared/private
memory; unavailable values stay unknown. If a PSS guard is declared, recommendations require a known,
compliant PSS peak. On unsupported platforms, omit that optional limit and retain RSS, availability
and swap guards. The watchdog is sampled and can miss transient peaks.

Use the screen to eliminate clearly poor thread/worker combinations. Do not install its fastest
single repetition as a default. Confirm finalists and a fresh reference in one matrix, with at least
20 accepted images per repetition and three rotating-order repetitions. Use enough images to exercise
several full batches and expensive recipe choices; 48 measured images plus two separate warmups is
our current production comparison. Repeated seeds measure execution variation, not independent scene
diversity. A substantially changed workload, sparse expensive recipes or a different seed distribution
can require a longer confirmation. Do not lower quality or leave workers idle to make a case fit.

The study inspects each completed pool and requires exact encoded image and content/mask/annotation
signatures. It records a workload/software/performance-implementation context, a coarse hardware class,
initial/minimum available RAM, swap-out growth and actual resource observations. It isolates its own
observations from production ETA calibration. Any abort ends the comparison and retains partial
evidence. Partial runs cannot establish completed memory peaks or accepted-output throughput.

## 3. Select and explicitly apply a local recommendation

```sh
uv run python -m dataset_generator_m1 execution recommend \
  --config configs/local/my-production.yaml \
  --study outputs/tuning/confirmation/summary.json \
  --output-dir outputs/tuning/choice

uv run python -m dataset_generator_m1 preflight \
  --config configs/local/my-production.yaml \
  --overrides outputs/tuning/choice/recommended-overrides.yaml \
  --output-dir outputs/my-next-pool
```

The recommender requires a complete guarded study, matching workload/software/hardware class, clean
immutable source, equal image/evidence hashes, inspected pools and complete repeated counters. Run
size and seed may change; other generation distributions, QA/telemetry costs, source content, output
sizes or implementation/software changes invalidate compatibility. The hardware class contains OS,
architecture, logical/usable CPU counts and a rounded RAM class, with no hostname or device identifier.

It first excludes policies that no longer fit the current CPU budget or host-memory headroom. Required
available RAM is the largest observed host-memory drop across that policy's repetitions, multiplied
by 1.10, plus the experiment's recorded available-memory reserve. This is a local empirical safeguard,
not a hard bound or a substitute for runtime monitoring. Other host activity can distort it; rerun
when the environment was noisy or capacity changes materially.

Among eligible policies, take the best median accepted throughput. By default, consider configurations
within 5% of that median and prefer the fewest workers, then the lowest requested CPU concurrency,
then sampled RSS. This avoids spending extra RAM/processes for a small timing difference. Set
`--tolerance-percent 0` to select the highest median instead. The report shows observed min/max and
all exclusions; three repetitions do not justify a formal confidence interval or significance claim.

The output contains `result.json` and `recommended-overrides.yaml`. The override changes only measured
worker, native-thread, queue and decoded-cache settings, preserving the original composer's resource
budgets. Trial safety ceilings are not installed as normal-generation budgets. Preflight continues to
show the conservative RSS plan and its warnings, even if an explicit measured policy exceeds that
forecast's default RAM budget. Neither result silently rewrites a composer, profile, ETA cache or
future run. Copy a reviewed override into `configs/local/` or apply the same typed leaves to a saved
composer. Use it explicitly with preflight/generate; run a new tuning study on another machine.

The configuration cockpit, guided preflight and atomic preflight show effective workers, OpenCV
threads, in-flight window, RSS estimate and planning budget. Automatic capacity is labelled separately
from evidence about speed. Standard profile defaults and rendering quality remain unchanged.

## When to stop testing

Stop a worker-count escalation when guard failures consume the session's reserve. Look for a stable
throughput plateau among affordable counts, then select a smaller near-best policy. Higher counts
are useful again after a scheduling/transport or rendering-cost change, a different workload, or more
hardware headroom. They are not necessary to finish every Cartesian product. Hardware-class defaults
still require additional environments under #28; a local winner is not a universal formula.
