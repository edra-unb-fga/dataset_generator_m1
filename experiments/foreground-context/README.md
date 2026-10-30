# Guarded foreground-context studies

The saved `local-cpu-policy.json` provides a conservative starting point for the
local CPU machine: two workers, one native thread each, a minimum available host
reserve, adaptive RSS ceiling, 16 MiB additional host swap-out limit, and a
30-minute timeout per phase. These are starting choices, not a universal optimum.
The host must have sufficient headroom when the command starts. Copy and change
the policy for another machine; the resolved limits and observed memory are frozen
in each study directory. Do not weaken limits automatically after a guard fires.

From the repository root, run the development study first:

```sh
uv run python scripts/guarded_foreground_context.py \
  --config examples/configs/landing-pad_minimal.yaml --phase development --samples 20 \
  --output-dir outputs/experiments/foreground-context-development
```

After reviewing development and freezing the study matrix, use a fresh directory
for the reserved study:

```sh
uv run python scripts/guarded_foreground_context.py \
  --config examples/configs/landing-pad_minimal.yaml --phase reserved --samples 12 \
  --output-dir outputs/experiments/foreground-context-reserved
```

Override `--policy` and `--matrix` with saved JSON files. The wrapper copies the
policy, matrix and launcher, records the measured basis, command, process-tree RSS,
available memory and host swap-out, and retains logs and an outcome even when the
study is stopped by a guard. Each run uses a fresh output directory; prior pools
stay inspectable. Completed paired views and metrics are under `study/report.html`
and `study/summary.json`. A guard stop is not a completed comparison. Monitor
measurements are sampled and total process RSS can count shared pages more than once.
Development and reserved seeds differ, but use the same source assets; they are
not a real-image or asset-held-out evaluation.

## Colab CPU: independent development and reserved phases

Build one immutable bundle after all relevant code changes have been finalized:

```sh
python3 experiments/foreground-context/build_colab_bundle.py \
  --output outputs/experiments/foreground-context-colab/input-final.tar.gz
```

The saved `colab-supervisor-policy.json` controls allocation and timing bounds; change
it before building the bundle. Both phases and their freeze must use the identical
policy bytes embedded in that bundle. The supervisor requires the 3D reserved
phase to be closed before it will allocate either 2D phase.

The archive contains the 2D source, locked dependencies, study matrix and policy,
and the real configured foregrounds and backgrounds. No Git clone is needed. The
supervisor holds the 3D study's budget lock throughout each 2D allocation. It charges
closed allocations by actual start/end time, protects the full 45-minute 3D reserved
allowance if unused, and reserves 15 minutes for each unrun 2D phase. Each phase has
an independent shutdown watchdog at 14 minutes; remote execution is shortened after
allocation/upload to preserve 210 seconds for phase upload, packaging, retrieval and
timeout overhead. These bounds depend on Colab and network responding; failed or
unconfirmed shutdown requires reconciliation and is never silently retried.

Run the supervisor detached so it can retrieve results and stop the runtime even if
the initiating agent disconnects (replace `input-final.tar.gz` only with a verified
bundle):

```sh
nohup uv run python experiments/foreground-context/colab_supervisor.py run \
  --phase development --session context-development \
  --bundle outputs/experiments/foreground-context-colab/input-final.tar.gz \
  --three-d-root outputs/experiments/realism-round-l4 \
  --output outputs/experiments/foreground-context-colab/run \
  > outputs/experiments/foreground-context-colab/development-supervisor.log 2>&1 < /dev/null &
```

After reviewing the retrieved development archive, write a review file and freeze it:

```sh
uv run python experiments/foreground-context/colab_supervisor.py freeze \
  --output outputs/experiments/foreground-context-colab/run --review /absolute/path/to/review.md
```

Run the reserved phase with the same bundle and a new session name:

```sh
nohup uv run python experiments/foreground-context/colab_supervisor.py run \
  --phase reserved --session context-reserved \
  --bundle outputs/experiments/foreground-context-colab/input-final.tar.gz \
  --three-d-root outputs/experiments/realism-round-l4 \
  --output outputs/experiments/foreground-context-colab/run \
  > outputs/experiments/foreground-context-colab/reserved-supervisor.log 2>&1 < /dev/null &
```

Each phase retains the frozen allocation basis, per-phase provenance, shutdown
status, remote logs, and a SHA-256-verified result archive. Generation uses two
workers and one native thread at the original 1280² configuration. Compute
accepted images per second from each variant's accepted count and generation wall
time inside the archive; report setup, peak sampled process-tree RSS and host swap
separately. Do not compare that rate directly with a local run made on different
hardware. Development and reserved scenes use different seeds but share the asset
catalog; they are not an asset holdout or evidence of real-image performance.

A closed development attempt that failed during bundle upload can be retried once
only with `--retry-failed-development`. The original ledger and attempt directory
remain intact; the retry uses `development-retry-01`, records its own allocation,
and must use the identical frozen input bundle and supervisor policy. The budget
check includes the original allocation. Chunk uploads are capped at 32 MiB and each
chunk and the reassembled archive are hash-checked before execution. A successful
retry is selected for review and freeze; other failure types require investigation
and cannot be retried with this option.
