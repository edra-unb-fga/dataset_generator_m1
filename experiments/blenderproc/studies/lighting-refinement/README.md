# Matched lighting refinement

**Historical run:** Local `/tmp` files, usage snapshots, rates, session names and CU reservations below describe the original study and are not reusable authorization or current evidence. For a new run, check idle sessions and rates, record a fresh baseline and recalculate the aggregate reservation and budget. Rebuild and verify inputs from the current source and assets.


The previous paired screen found that reducing all lamp powers to 60% darkened already dim indoor targets without reliably removing hotspots. This follow-up holds scene, target, wear, exposure, lamp positions, type, color and original power fixed in each triplet. It compares:

- `baseline`: original lamps, retained as the bright-stress reference.
- `soft`: double emitter size (capped at 3 m), widen spot angle 1.5 times (capped at 2.4 rad), and increase spot blend by 0.3 (capped at 1).
- `soft-fill`: the soft treatment plus a 120 W, 1 m warm area light at (0, 0, 2.5 m), aimed at the origin.

This is an engineering screen, not calibrated lighting. Broadening a source can change target illumination and brightness, and fill increases total power. Indoor geometry can reposition or omit an emitter; inspect `resolved_lamps` in each result and do not assume the fill actually contributes. The renderer zeros the world strength indoors, so raising world strength would not provide indoor fill. The first two original images per group are preselected stress candidates, not proven glare cases; inspect all originals and retain actual bright cases separately. The experiment does not itself change production distributions.

Use outdoor forced `night-single` and indoor presets, eight matched scenes per condition and 48 renders per round. Offset 40 gives new deterministic procedural seeds relative to the earlier offsets 0–19. A later adaptive round should choose changes after visual inspection and use a nonoverlapping offset (e.g. 48), preserving the baseline and making the treatment change explicit. A small sample is qualitative and forced conditions do not estimate production prevalence. Require complete accepted triplets, exact masks, lamp transforms and matching non-lighting controls; assess targets, local clipping, hotspot size, shadow plausibility, underexposure and omitted or repositioned lamps. Do not promote a default from this screen alone.

## Run control

The controller is adapted from the paired-lighting supervisor, with a **3 CU aggregate hard cap** in both pre- and post-allocation checks. Supply a fresh idle usage snapshot from before *all new attempts* and an explicit conservative reserve covering all other new attempts, including partially completed or failed ones. It uses the larger of that reserve and observed balance decrease (plus rounding), then adds the forecast through the watchdog. The earlier round's baseline and reserve must not be reused for this new authorization. The parent supervisor uses twice the recorded prior single-L4 rate for its preflight forecast and rechecks the actual allocation rate. The 3 CU gate is an estimate, not a provider-enforced limit; delayed billing, rate changes, network failures or failed shutdown can defeat it. Never overlap sessions. Confirm the prior assignment is stopped and the account is idle before each new allocation.

The remote time budget includes setup, rendering, verification and archiving, and may expire before completion. An independent watchdog attempts shutdown. The controller retrieves and checks archive hash and size, then stops the session; inspect status, metadata, logs and after-usage. Partial archives are evidence of partial work, not a completed comparison. Source, input and execution fingerprints are sealed in the bundle and each prepared study contract. The verifier checks all non-lamp job fields including wear hashes, exact lamp transforms, accepted results and full mask arrays.

A prepared local bundle at `/tmp/lighting-refinement-input/` was built from the verified prior paired bundle's input config and the current workspace sources. It has input SHA-256 `115c9439d6adc54c43d554f693706064e93ab5473d303464cffde5ab11fc99fe` and identity `e868e0cceeacc8d62a77e1dc9bad276d13729fd61583898d398497840ed19fb6`. Its spec sets 600 remote seconds, eight scenes per condition and offset 40. It includes this study's scripts with matching hashes. Temporary paths and current source state must be rechecked before use; rebuild the bundle after any source edits. The prior paired bundle's validated input was unpacked with its recorded SHA-256 and used as the config source, so asset and reference hashes remain recorded.

After verifying the baseline, account and rate evidence, launch with a fresh output path:

```bash
python3 experiments/blenderproc/studies/lighting-refinement/supervisor.py \
  --input-dir /tmp/lighting-refinement-input \
  --scripts-dir experiments/blenderproc/studies/lighting-refinement \
  --output /tmp/lighting-refinement-run --session lighting-refinement \
  --watchdog-seconds 780 \
  --rate-evidence outputs/experiments/realism-camera-round/l4-completion/controller.log \
  --budget-baseline /path/to/fresh-idle-before-new-rounds.txt \
  --prior-spend-reserve CONSERVATIVE_CU_FOR_ALL_NEW_PRIOR_ATTEMPTS
```

After any changes, rebuild from a verified, unpacked prior input config and prepare a new spec with hashes. The bundle CLI creates a bootstrap next to the archive:

```bash
PYTHONPATH=src uv run python \
  scripts/blenderproc_pilot.py bundle --config /tmp/lighting-refinement-prior/config.json \
  --output-file /tmp/NEW-INPUT/input.tar.gz
cp scripts/generate_scene_presets.py /tmp/NEW-INPUT/generate_scene_presets.py
```

Create `spec.json` with SHA-256 fields `bundle_sha256`, `bootstrap_sha256`, `cli_sha256`, `remote_sha256`, plus `total_seconds`, `scenes_per_condition` (1–8), and `scene_offset` (0–10000); confirm the bundled `transform.py` and `verify.py` hashes match local files. Changes to the spec are not an authorization to exceed the shared CU cap.

The first round was launched with that bundle before a local verifier improvement requiring both `visible` and `full` arrays. After retrieval, rerun the current `verify.py` locally on the extracted `results` directory with `8` as the count. A separately sealed follow-up input is `/tmp/lighting-refinement-input-v2/`, SHA-256 `82e769621e0ba9843d031e5b13f97fb4a6e74259e2cb80db58e871dde1e8f593`, identity `7897602320e7710b9d95614290817690a3b876a15fd2aa9255561e6ce7ebca52`. Its spec uses offset 48, but a second round should be chosen only after reviewing the first and rechecking the shared budget; this is not evidence of an adaptive treatment choice.

## Local review

Once the controller has closed and its archive is retrieved, create a fresh local review without modifying the run or its inputs:

```bash
uv run python \
  experiments/blenderproc/studies/lighting-refinement/postprocess.py \
  --run-dir /tmp/lighting-refinement-run \
  --input-dir /tmp/lighting-refinement-input \
  --output /tmp/lighting-refinement-review
```

The processor verifies the archive size and SHA-256, sealed input hashes, remote spec, bundle identity, source fingerprints, strict triplet controls and masks, and accepted image and mask checksums. It copies the sealed inputs and available controller evidence, records the result archive checksum and location, extracts a separate recovery copy, and writes `metrics.json`, `verification.log` and a filterable triplet-adjacent `index.html` with fullscreen comparison. Display-pixel mean and bright/dark fractions use the union of visible masks and are not calibrated luminance measurements. If evidence is missing, incomplete, invalid or shutdown is unconfirmed, the review says so and the command exits 2; an archive or input checksum failure aborts. Inspect `warnings`, source fingerprints, scene metadata and actual resolved lamps along with the images.

## Adaptive second round

Visual review of the first round (`outputs/experiments/lighting-refinement-round1-reviewed/REVIEW.md`) found that broadening alone did not consistently remove bright pools and the 120 W fill often increased highlight pressure, while some dim cases benefited from fill. The separately scripted `round2` keeps the original baseline, then compares broadened geometry with each original lamp's power multiplied by 0.8 and the same treatment plus a 60 W fill. This is a combined candidate treatment, not an isolated estimate of geometry or power. It retains original-intensity stress candidates and pairs every scene. Use nonoverlapping offset 48. Review clipping and dark cases separately before proposing defaults.

The round-two scripts are in `round2/`; the first-round bundle remains immutable. Use the parent `supervisor.py` with `--scripts-dir experiments/blenderproc/studies/lighting-refinement/round2`, and produce a fresh input bundle and spec with matching round-two remote checksum. The postprocessor should receive `--study-scripts experiments/blenderproc/studies/lighting-refinement/round2` so its strict verifier uses the round-two transform. Run `round2/test_study.py` to check controls, mask rejection and duplicate extraction. The shared budget baseline and conservative reserve must include every new-round attempt; no overlapping cloud sessions.
