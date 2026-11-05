# Fresh-seed natural mixture screen

This bounded, opt-in 24-scene study uses `pilot-lighting-refined-candidate.example.json`'s actual nine-member mixture, a fresh seed and the retained reference pool. Scene/context and lighting membership follow weights; exact counts and extreme-light prevalence are not guaranteed. The reference pool and asset bytes are reused and are not a held-out asset set. The first paired screen indicated broad lighting improved some saturated areas but left washed-out cases; review both bright and dark natural cases and do not infer realism or detector quality.

Use a freshly rebuilt portable bundle with the verified source assets and the refined candidate's full `procedural` field. Seal `spec.json` with hashes `bundle_sha256`, `bootstrap_sha256`, `cli_sha256`, `remote_sha256`, and numeric `total_seconds` (at most 750), `scenes` (1–40), `seed` and `scene_offset`. Confirm the bundle contains this `remote.py` and `verify.py` matching local hashes. The parent lighting-refinement supervisor supports this script directory and applies its conservative **3 CU aggregate cap**, prior-attempt reserve, actual-rate checks, adaptive resource guards, independent watchdog, retrieval checks and shutdown. Recheck account-wide active assignments, fresh idle balance, price/rate evidence and all prior attempt costs immediately before allocation. Do not run duplicate attempts or infer complete results from a partial archive.

```bash
python3 experiments/blenderproc/studies/lighting-refinement/supervisor.py \
  --input-dir INPUT --scripts-dir experiments/blenderproc/studies/coordinated-candidate/natural \
  --output FRESH_OUTPUT --session natural-lighting --watchdog-seconds 780 \
  --rate-evidence VERIFIED_L4_RATE_LOG --budget-baseline BEFORE_FIRST_ATTEMPT_IDLE_USAGE \
  --prior-spend-reserve CONSERVATIVE_ALL_PRIOR_ATTEMPTS_CU
```

After the supervisor confirms closure and retrieval, produce a verified gallery:

```bash
PYTHONPATH=src .venv/bin/python experiments/blenderproc/studies/coordinated-candidate/natural/postprocess.py \
  --run-dir FRESH_OUTPUT --input-dir INPUT --output FRESH_REVIEW
```

The verifier checks the sealed study, unique accepted job identities, image/mask SHA-256 values and mask fields. The local recovery rejects archive and bundle checksum differences, source fingerprint mismatches and unconfirmed shutdown, retaining incomplete outputs separately. It only builds a gallery when complete. Its generated HTML uses the existing project report tooling. It has focused synthetic fixture coverage, but no successful real recovered archive has yet been exercised through this postprocessor. Independent visual review remains required.
