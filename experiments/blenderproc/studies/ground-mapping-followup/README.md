# Ground mapping paired follow-up

This bounded study uses six matching candidate scenes for legacy mapping and fixed 0.5, 1.0 and 1.5 view-relative spans, plus two separately paired 1024-pixel close views. The same seed and 12-scene reference pool can exercise open, outdoor and indoor contexts as well as wear and reflective cases; inspect the prepared jobs rather than assuming a distribution. Comparisons are only within the same-resolution pairs. The verifier compares scene controls and mask arrays including dtype, shape and hash and records ground diagnostics; achieved spans may differ when clamped or coverage fails. These controls are qualitative material studies, not measured physical realism.

Prepare a local candidate config with all paths and ground manifest identities checked, `scenes: 6`, and `ground_mapping` enabled. The staged screen used seed 20261029. Build the portable bundle using `uv run python scripts/blenderproc_pilot.py bundle --config CONFIG --output-file INPUT/input.tar.gz`; retain the resulting bundle and bootstrap hashes and identity. Copy `scripts/generate_scene_presets.py` into INPUT. Create `spec.json` with `bundle_sha256`, `bootstrap_sha256`, `cli_sha256`, and `remote_sha256` for the respective files and this directory's `remote.py`, plus `total_seconds` no greater than 750. Input paths remain relative to the unpacked workspace, where all derived configs are written. The bundle seals source, reference, artwork, asset manifests, map hashes and wear derivatives; do not substitute files after sealing.

```bash
python experiments/blenderproc/studies/ground-mapping-followup/supervisor.py \
  --input-dir INPUT --scripts-dir experiments/blenderproc/studies/ground-mapping-followup \
  --output FRESH_OUTPUT --session ground-mapping-followup --watchdog-seconds 1050 \
  --rate-evidence PRIOR_SINGLE_L4_USAGE_LOG \
  --budget-baseline USAGE_BEFORE_FIRST_ATTEMPT --prior-spend-reserve PRIOR_CU_UPPER_BOUND
```

The baseline must be an idle-account snapshot from before the first attempt. The caller must provide a conservative upper bound for all previous attempts; for two 1050-second attempts at 3.08 CU/hour, use `1.80`. The gate uses the larger of that reserve and the observed balance decrease plus rounding, then adds a conservative forecast to the watchdog and rejects an estimate over the cumulative 5 CU cap. It repeats the gate with the observed rate immediately after allocation. Account snapshots and assumptions are retained. The historical rate is not a price guarantee and delayed billing, changed pricing or failed shutdown can defeat an estimated cap.

The supervisor verifies and chunks the bundle, retrieves a checksummed archive, and stops the session, with an independent stop watchdog. The remote 750-second limit includes setup, leaves recovery time, logs GPU telemetry and preserves partial outputs on handled failure. Check the final status, watchdog and cost records before further allocation. A failure or timeout may leave incomplete pairs; treat the image archive as partial evidence and do not claim mask equivalence until the verifier reports success.

## 2026-10-30 screen

The L4 screen completed all 28 images: four mapping variants in six 640-pixel scenes and two
1024-pixel close-view pairs. The verifier found exact matching full and visible masks in each
comparison, and all 20 mapped results reported achieved spans and coverage without clamping.
Only two of the three configured grounds appeared. In the visual review, soil features became
conspicuously large at 0.5 in some views; 1.0–1.5 appeared more moderate, concrete changed less,
and a bright indoor scene remained washed out in both close-view variants. This small screen does
not establish a universal scale or real-image fidelity. The full gallery, review, archive, telemetry,
contracts and verifier output were retained in ignored `outputs/experiments/ground-mapping-followup/`;
they are local experimental evidence, not shipped repository assets.

The input bundle SHA-256 was `f5a27ebb5e46b4930b70a7bdfadacfa16ab7892097550cb10dc1a4b577414500`;
the retrieved archive was `a91d232a9cbd8775849dd1454c10e97f262235255228ef512bf19df258c93da6`.
The runtime stopped and the balance moved from 156.19 to 156.03 CU at displayed precision; billing
can lag. Source, renderer, asset and reference fingerprints are in the archived contracts.
