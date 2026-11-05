# Balanced completion retry

**Historical run:** Local `/tmp` files, usage snapshots, rates, session names and CU reservations below describe the original study and are not reusable authorization or current evidence. For a new run, check idle sessions and rates, record a fresh baseline and recalculate the aggregate reservation and budget. Rebuild and verify inputs from the current source and assets.


The first completion attempt stopped before rendering because its newly measured RSS limit was 41.029510 GiB, lower than the original policy's 41.059277 GiB. The recovered archive and status confirmed failure and runtime stop. Study identity includes the execution catalog, so changing its resource guards changes the identity even when every scene job is identical.

This retry uses the original input bundle, original full candidate-1 plan and original reference pool. It derives fresh hardware guards and takes the stricter value for each guard from the original and fresh policies; execution profiles must otherwise match. Before rendering, it checks the original study fingerprint, exact equality of all 100 scene jobs, all contract fields other than the execution-dependent runtime hash, and the regenerated runtime and study fingerprints. It renders candidate IDs 069–099 and held-out seed IDs 000–019. The held-out seed reuses the reference pool. The archive preserves the original study, chosen policy and fresh policy and basis. The new study identity is distinct and must not be represented as the original identity.

Stage the verified inputs into a new directory:

```bash
python3 experiments/blenderproc/studies/balanced-completion-retry/stage.py /tmp/balanced-completion-retry-input
```

Run only after confirming an idle account and reconciling all reservations. The known reservations are 0.668 CU for lighting and 0.9 CU for the failed completion: 1.568 CU total. This attempt reserves another 0.9 CU, giving 2.468 CU against the 3 CU shared ceiling. Increase `--reserved-before` to include any further allocations; never run shared-budget sessions concurrently.

```bash
python3 experiments/blenderproc/studies/balanced-completion-retry/supervisor.py \
  --input-dir /tmp/balanced-completion-retry-input \
  --scripts-dir experiments/blenderproc/studies/balanced-completion-retry \
  --output /tmp/balanced-completion-retry-output \
  --session balanced-completion-retry --watchdog-seconds 1050 \
  --baseline "$FRESH_IDLE_BASELINE" --reserved-before "$PRIOR_RESERVED_CU" \
  --rate-evidence "$RATE_EVIDENCE"
```

The gate adds 0.01 CU to the displayed balance decrease, uses the larger of that buffered decrease and prior conservative reservations, and limits the watchdog estimate to the 0.9 CU reservation. The 750-second remote deadline and independent 1,050-second stop watchdog do not create a provider-enforced cap; billing delay, network failure and failed stop can defeat cost or recovery estimates. Inspect status, checksum, guard, budget, GPU and stop evidence after execution.

To verify and build a separate filterable, fullscreen gallery of original and recovered results:

```bash
python3 experiments/blenderproc/studies/balanced-completion-retry/collect.py \
  --completion /tmp/balanced-completion-retry-output \
  --output /tmp/balanced-completion-retry-review
```

The collector labels partial results and validates archive, policy, study, source, job and accepted RGB/mask hashes. These checks do not establish visual quality or detector performance.
