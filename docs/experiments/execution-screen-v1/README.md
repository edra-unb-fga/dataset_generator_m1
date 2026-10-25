# Local execution screen v1

Three rotating-order repetitions of five execution policies, twenty measured outputs each and two
separate warmup outputs per policy/repetition. Total: 300 measured and 30 warmup images. The fixed
landing composer is 320×240, current-fast, 1–2 requested objects, one QA sample. This is intentionally
small diagnostic work, not the intended production workload or a hardware-class recommendation.

All measured pools completed, passed inspection, and had identical geometry/annotation/mask signatures.
The compact JSON preserves raw bundle hash, software, policies, stage work, counts, sampled RSS peaks
and working-tree provenance above `9d34516`. Raw pools and local observations remain ignored. Resource
peaks are sampled, not guaranteed instantaneous maxima; background OS load was not controlled.

Observed active seconds for twenty accepted outputs:

| Policy | Three repetitions |
| --- | --- |
| configured: one worker, backend native default | 9.11, 10.09, 9.00 |
| one OpenCV thread | 9.93, 9.92, 10.41 |
| one OpenCV thread + 64 MiB decoded cache | 9.91, 9.86, 10.87 |
| two workers, one thread each | 10.78, 10.45, 10.01 |
| two workers, one thread each, window of two | 10.54, 11.06, 10.98 |

There is no convincing benefit from caching or two workers on this tiny workload. Spawn/startup and
small-task overhead matter; a result at intended image size/source reuse may differ substantially.
No default is changed, and no universal speedup or slowdown is claimed. Explicit controls remain
available for the next computer. Compare native-thread controls against configured, cache against
threads-one, workers against threads-one, and queue-two against two-workers—not every row against a
baseline with several simultaneous differences.

Run `benchmark --production` as documented in `docs/EXECUTION.md`, then reproduce with larger intended
inputs and additional hardware before curating a generic execution profile. Rolling scheduling, worker
setup reuse, polygonization reuse, synthesized-background caches and shared-memory transport were not
implemented or promoted based on this screen. They remain independent experimental candidates.
