# Balanced candidate completion

**Historical run:** Local `/tmp` files, usage snapshots, rates, session names and CU reservations below describe the original study and are not reusable authorization or current evidence. For a new run, check idle sessions and rates, record a fresh baseline and recalculate the aggregate reservation and budget. Rebuild and verify inputs from the current source and assets.


This continues the interrupted original study using its sealed input bundle. The recovered candidate-1 study identity is `845dc41c3bea849d7fc7ec41e4dfd3ea95e2e303326960cb445d6f7894a11b1c`. Its configuration uses seed `20261026`, scene offset `100`, and 100 locally numbered jobs. Jobs `000-base-fast` through `068-base-fast` were accepted; render only `069-base-fast` through `099-base-fast`. The held-out chunk uses seed `20261117`, offset `0`, and jobs `000-base-fast` through `019-base-fast`. The held-out seed still uses the original reference pool.

Original evidence:

- Input bundle SHA-256: `aced5844c1a37b545a2bd4d0dec061d97d49382fa1695c12dc6ac953afd276a3`.
- Recovered result archive SHA-256: `323c69c48c70b0f4729ff2d9452ae2a5a0e11527e8bc98577f6c3c8a1c8bd2d9`.
- Original execution policy SHA-256: `4505f03ffc6ccefcf07646b0264308838fa53e10e2bd3990972b7401beaec83f`.
- Bundle bootstrap SHA-256: `b6cdfb6aa72d8336f0cbea8ee7dfe62a96ba2622cb3e6d7b23be72c3b5b721d6`.
- Preset CLI SHA-256: `c4044bf47bf11e2a0e460f4f697bafa0f87eae9e59a2cbcac0645be6e62f6cfd`.

From the worktree root, stage to a **new** directory. Staging checks the bundle and result archive, study contracts, accepted job records and image/mask hashes; it refuses a changed accepted set.

```bash
python3 experiments/blenderproc/studies/balanced-completion/stage.py /tmp/balanced-completion-input
```

The controller below allocates a Colab L4. Run only after checking the shared budget ledger and confirming that the account is idle. `--reserved-before` is the sum of conservative reservations for all earlier allocations in this round, including lighting, even if billing has not settled. Use the fresh round baseline; the example value of zero applies only before any other allocation in this round. Do not run shared-budget allocations concurrently.

```bash
python3 experiments/blenderproc/studies/balanced-completion/supervisor.py \
  --input-dir /tmp/balanced-completion-input \
  --scripts-dir experiments/blenderproc/studies/balanced-completion \
  --output /tmp/balanced-completion-output \
  --session balanced-completion \
  --watchdog-seconds 1050 \
  --baseline "$FRESH_IDLE_BASELINE" \
  --reserved-before 0 \
  --rate-evidence "$RATE_EVIDENCE"
```

The gate reserves 0.9 CU for this attempt and enforces a 3 CU aggregate ceiling against both prior conservative reservations and the displayed balance decrease from baseline, with a 0.01 CU rounding cushion. It requires idle usage, uses twice the recorded historical rate for the watchdog estimate, and checks the observed allocation rate. These estimates are not a provider-enforced spending cap; delayed billing, changed rates, or a failed stop can exceed them. Preserve the reservation until billing settles and reconcile before another allocation.

On the remote VM, the controller verifies the sealed inputs, generates current adaptive resource guards, and refuses to run if any original guard is weaker than its current counterpart. It reinstates the original policy and prepares the complete candidate-1 plan at the original paths; the regenerated identity must match before rendering the explicit missing IDs. It then renders the held-out chunk and verifies the completed IDs and accepted statuses. A different host may cause the guard or identity check to fail before rendering; do not relax either check to force a continuation.

A 750-second remote deadline reserves time for recovery. The controller downloads and checksum-verifies the result archive and attempts to stop the runtime; an independent 1,050-second watchdog also attempts a stop. Inspect `status.json`, logs, metadata, scene records, hashes, and the final account state. Handled failures can produce partial evidence; abrupt VM loss, network failure, a controller or host shutdown, or failed cleanup can defeat recovery or leave a runtime active. A completed run does not by itself establish realism or detector performance.

## Verify and review retrieved evidence

After retrieval, build a separate review directory without changing the original or recovered evidence:

```bash
python3 experiments/blenderproc/studies/balanced-completion/collect.py \
  --completion /tmp/balanced-completion-output \
  --output /tmp/balanced-completion-review
```

The collector verifies the archive and recorded result hashes, study and execution identities, allowed job IDs and held-out source/configuration. It produces `verification.json`, a metadata-rich `manifest.json`, and `index.html` using the shared filterable, fullscreen gallery builder. The gallery labels original candidate, recovered candidate and held-out seed separately; the held-out seed uses the original reference pool. A failed or incomplete recovery is labeled partial, and rejected scenes are excluded and recorded as warnings. Omit `--completion` to review the verified original 169 scenes alone. Hash verification does not assess visual quality.
