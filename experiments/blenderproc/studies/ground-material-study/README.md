# Ground material study workflow

**Status: experimental; findings pending.** This study uses the optional BlenderProc harness and the
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

No study outcome, default recommendation or real-image/model-transfer claim is established by this
protocol alone. Report results only against the exact saved matrix, assets, source and render settings.
