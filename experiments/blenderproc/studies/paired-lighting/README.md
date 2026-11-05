# Paired lighting screen

**Historical run:** Local `/tmp` files, usage snapshots, rates, session names and CU reservations below describe the original study and are not reusable authorization or current evidence. For a new run, check idle sessions and rates, record a fresh baseline and recalculate the aggregate reservation and budget. Rebuild and verify inputs from the current source and assets.


Question: Do materially dimmer coordinated lamps improve ordinary target visibility and reduce distracting bright pools while preserving plausible diversity? This is a synthetic visual screen, not calibration to real lighting, and watts are renderer parameters, not a universal lumen mapping. The candidate scales every sampled lamp's power by 0.60; other lighting, environment, placement, artwork, material, masks and random seed are paired. No spot-size or total-power cap is applied in this first isolated comparison.

The remote runner forces a single selected member and lighting choice: 20 outdoor scenes using the `outdoor` preset forced to `night-single`, and 20 using the `indoor` preset and its indoor lighting distribution. Each renders baseline and dim, for 40 pairs and 80 images. It retains the first two baseline images in each group as a predetermined 10% original-intensity stress subset, labeled `retained_intense_candidate` in pair evidence; inspect those to determine whether they actually exhibit glare. They are not proven glare cases, and this study does not implement a production mixture. Compare all 20 pairs; report stress cases separately and do not infer that this forced screen represents natural production frequencies. The verifier checks paired scene controls, lamp ratios and rendered mask bytes, and fails on incomplete or mismatched pairs. Verify scene identities, source fingerprints, complete status, ground diagnostics, hotspot/target contrast, perceived shadow plausibility, and both underexposure and highlight clipping before any proposal for defaults. User approval is required before promotion.

For the 2026-10-30 round, the mapping follow-up was required to finish, retrieve its archive, confirm shutdown and report an idle account before allocation. Three prior allocated attempts were conservatively reserved at 2.70 CU (three times 1050 seconds at 3.08 CU/hour, rounded up). Forecast at 3.08 CU/hour for another 1050 seconds was 0.8983 CU, so the conservative cumulative estimate was 3.5983 CU; it was above the 3 CU target and below the authorized 5 CU cumulative cap. The aggregate gate uses the higher of this reserve and observed balance decrease plus rounding; changed rates are checked after allocation. This is an estimate, not a provider-enforced spend cap. The initial before-first-attempt snapshot was `/tmp/balanced-multiscene-run/usage-before.txt` (156.52 CU). The supervisor captures the current idle usage, source and baseline hashes, rate evidence, post-allocation rate, transfer hashes and verified result archive; it independently attempts shutdown at the watchdog deadline. Network failure, abrupt VM loss, delayed billing or a failed stop can defeat recovery or the estimate. A future run needs fresh account, rate and budget evidence; do not reuse these values as current limits.

## Prepare and launch only after mapping is stopped

Use an independently checked local config with the intended holdout/reference pool, artwork, exact ground/HDRI manifests and maps, balanced procedural members, valid ground mapping, `seed: 20261029`, 640-pixel resolution and 32 fast samples. A suitable previously prepared input is `/tmp/ground-mapping-followup.json`; inspect and retain its exact contents and hashes before using it. The input bundle seals source, inputs and wear derivatives. Build only after edits to this study and other in-flight source edits are stable, and retain the bundle output's identity and source fingerprints:

```bash
INPUT=/tmp/paired-lighting-input
mkdir -p "$INPUT"
PYTHONPATH=src uv run python scripts/blenderproc_pilot.py bundle --config /tmp/ground-mapping-followup.json --output-file "$INPUT/input.tar.gz"
cp scripts/generate_scene_presets.py "$INPUT/generate_scene_presets.py"
```

Create the sealed spec after confirming the bundle contains this study's `verify.py` and the desired source state:

```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path
p=Path('/tmp/paired-lighting-input')
s=Path('experiments/blenderproc/studies/paired-lighting')
h=lambda x: hashlib.sha256(x.read_bytes()).hexdigest()
(p/'spec.json').write_text(json.dumps({'bundle_sha256':h(p/'input.tar.gz'),'bootstrap_sha256':h(p/'input.tar.gz.run.py'),'cli_sha256':h(p/'generate_scene_presets.py'),'remote_sha256':h(s/'remote.py'),'total_seconds':750},indent=2)+'\n')
PY
```

After confirming the mapping run is closed and no assignment remains, use a fresh output path. The prior L4 rate evidence must contain a single active assignment; the file below was used in the previous gate. Validate its availability before launch.

```bash
python3 experiments/blenderproc/studies/paired-lighting/supervisor.py \
  --input-dir /tmp/paired-lighting-input \
  --scripts-dir experiments/blenderproc/studies/paired-lighting \
  --output /tmp/paired-lighting-run --session paired-lighting \
  --watchdog-seconds 1050 \
  --rate-evidence "$RATE_EVIDENCE" \
  --budget-baseline "$FRESH_IDLE_BASELINE" --prior-spend-reserve "$PRIOR_RESERVED_CU"
```

The remote total of 750 seconds includes bootstrap, rendering and archive creation; it is not guaranteed to finish 80 renders. A timeout leaves partial evidence, which must not be represented as a complete paired screen. The supervisor verifies archive checksum and size, retrieves available results and attempts shutdown; inspect `status.json`, `result-metadata.json`, watchdog log, after-usage and `pair-evidence.json`. Store raw evidence under ignored outputs and build a gallery only from accepted results.

## 2026-10-30 screen

The L4 screen completed 20 outdoor-night and 20 indoor pairs at 640 pixels. The verifier checked
scene controls, 0.6 lamp-power ratios, wear-map hashes and exact full/visible masks across each pair.
Independent review found lower lamp power darkened the images, but bright pools and washed-out
targets sometimes remained; some already-dark indoor targets became harder to distinguish. The
result does not support blanket dimming as a complete solution. Evaluate lamp geometry, spot spread,
fill and exposure in matched contexts; preserve deliberately intense cases without assuming the
preselected original-intensity samples necessarily contain glare. A single forced-condition seed
sequence does not establish ordinary mixture prevalence or calibrated realism.

The local ignored evidence under `outputs/experiments/paired-lighting-run/` includes the paired
gallery, independent review, per-image display-pixel metrics, verifier, input bundle, full archive
and execution records. Input SHA-256 was `4642833e6f4c3d8b492eae6e33bb9c233a0c4c943534fa8657fc643d2781a902`;
archive SHA-256 was `5c866740bd5c6bd6504083ef3fb4a966edb11d035eb5ab70201ec2070bcce42e`.
The final usage snapshot showed zero active assignments; displayed balance fell from 156.03 to 155.92
CU for this screen and from 156.52 to 155.92 CU across the round. Billing may lag.
