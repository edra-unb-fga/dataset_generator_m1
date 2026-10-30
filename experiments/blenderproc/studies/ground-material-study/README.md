# Ground material study workflow

**Status: completed bounded engineering screen; controls remain experimental.** The
[visual report](../../../../docs/experiments/ground-material-study-v1/index.html) records 18 initial
and six contextual GPU cells, exact paired masks, local tangent checks and limitations. This study uses the optional BlenderProc harness and the
[ground material controls](../../../../docs/GROUND_MATERIALS.md). Source manifests, inputs, configs,
seed, source identity and render policy must be retained with each run. Raw generated pools and
archives remain ignored; no cleanup is automatic.

1. Prepare the reference pool, artwork, two or more hash-verified PBR ground manifests and an HDR
   environment using the [pilot setup](../../README.md). Set a distinct explicit primary and donor for
   paired variants.
2. Define bounded treatments and mapping in a saved config; inspect resolved jobs, source fingerprints
   and map coverage before starting rendering. Keep camera/geometry and execution settings fixed
   across material comparisons.
3. Run the study with the existing driver and guards, retain completed and failed evidence, and check
   mask/geometry signatures plus full scenes and native-size crops. A completed render alone is not a
   visual or physical acceptance verdict.
4. Review effect visibility, seams, texture scale and material coherence, including diagnostic stress
   variants. Record unknowns, selected failures and limitations before compact evidence is promoted.

`matrix.json` is the 18-cell screen; `context-matrix.json` is the six-cell follow-up. The follow-up
also uses the explicit 5 mm thickness and one-metre panel width saved in its source bundle's base
configuration; the first screen used the pilot's 3 mm thickness default. Preserve those base settings
alongside the matrix when reproducing it. `source-hashes.json` records the original driver/fixture
definitions, while the report's `provenance.json` binds each actual input bundle and result archive.

Use `driver.py --config BASE --matrix MATRIX --output-dir NEW_OUTPUT --blenderproc EXECUTABLE
--blender-install-path DIRECTORY --total-seconds BUDGET --validate-only` to check prepared intent
locally. Remove `--validate-only` to render with the saved execution policy. The controller's
`spec.json` requires SHA-256 for input bundle, bootstrap and matrix, plus a positive remote budget
of at most 1200 seconds. The watchdog must allow at least 180 seconds beyond that budget. Outputs
must be fresh; retrieval verifies size and checksum, and failures/unconfirmed stop return nonzero.

No real-image/model-transfer claim is established by this protocol alone. Report results only against
the exact saved matrix, assets, source and render settings. RGB-only/donor-mismatch modes have not been
promoted to normal scene distributions.
