# Balanced 3D candidate study

This experimental study prepares two contiguous 100-scene chunks and a 20-scene held-out seed chunk. It uses the opt-in candidate and the normal physical pilot; randomized mixture weights do not guarantee exact quotas. The held-out seed still uses the supplied reference pool. Assess the actual completed jobs and their sampled controls before drawing conclusions.

Copy `pilot-balanced-candidate.example.json` to a local configuration, set all input paths and explicitly verify the manifest IDs and ground eligibility. Set six or more valid reference scenes, `scenes` to 100 and the desired seed. Build a portable, hash-verified bundle with `uv run python scripts/blenderproc_pilot.py bundle --config CONFIG --output-file INPUT/input.tar.gz`. The command also writes `input.tar.gz.run.py`. Copy `scripts/generate_scene_presets.py` into INPUT. Write `spec.json` containing SHA-256 values for `input.tar.gz`, `input.tar.gz.run.py`, `generate_scene_presets.py`, and this directory's `remote.py`, under `bundle_sha256`, `bootstrap_sha256`, `cli_sha256`, and `remote_sha256`; set `total_seconds` to at most 750. Preserve the bundle output's source/input identity and hashes with the run. Bundle config paths are relative to the extracted workspace root.

```bash
python experiments/blenderproc/studies/balanced-candidate/supervisor.py \
  --input-dir INPUT --scripts-dir experiments/blenderproc/studies/balanced-candidate \
  --output FRESH_OUTPUT --session balanced-candidate --watchdog-seconds 1050 \
  --rate-evidence PRIOR_SINGLE_L4_USAGE_LOG
```

The supervisor checks an idle account, the recorded historical rate, a conservative rate multiplier, and estimated time to the watchdog. Its gate is per-run; when multiple runs share a budget, independently account for all prior spend before launch. It stores account snapshots, splits and checks uploads, and uses a separate stop watchdog. The remote deadline includes setup and rendering, reserves time for recovery, records GPU telemetry, and archives partial output on handled failure. The controller verifies the downloaded archive and stops the named runtime. Network failures, abrupt VM loss, delayed billing, changing prices or stop failures can defeat recovery or a cost estimate; the estimate is not a provider-enforced cap. Inspect `status.json`, logs, source/input identities, render results and diagnostic records, including clamping and rejected jobs. No runtime outcome establishes real-world realism or detector performance.
