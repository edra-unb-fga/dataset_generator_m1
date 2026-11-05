# Coherent-scene studies: evidence index

The later [coherent-varied 2D screen](2026-11-05-2d-screen.md) adds fresh-seed comparisons,
an independent visual review, a motion-blur replay and exploratory throughput observations. The
[coordinated 3D lighting screen](2026-11-05-3d-screen.md) compares three matched lamp treatments.

These synthetic engineering studies prepared selectable candidates; they do not approve a default,
establish real-image realism, or establish detector performance. Their full native images, per-sample
settings and review galleries remain in ignored `outputs/experiments/` in the original worktree, not in
a fresh checkout. Preserve those local directories and original archives separately. The linked study
sources describe reproduction and source fingerprints; a reproduction using changed code or assets is
new evidence, not the historical run.

| Study | Coverage and finding | Source and locally retained review |
| --- | --- | --- |
| 2D coherent candidate and refined appearance | Each 67-pair-per-family gallery compares three families against matched `realistic-heavy` scenes. Refined wear reduced repeated oval marks but often looked clean and flat; reviewed examples did not establish strong target-crossing shadows. Single ordered timing passes are not robust benchmarks. | [2D study and recorded fingerprints](../../../experiments/foreground-context/coherent-study/README.md); local `coherent-2d-refined-gallery/terra-directed-review.md`. |
| 2D directional production gallery | 20 matched slots per family. Shared illumination and strong crossings were useful, but long straight bands recurred and common softness could affect small gauge details. | Same [2D study](../../../experiments/foreground-context/coherent-study/README.md); local `coherent-directional-production-gallery/INDEPENDENT-VISUAL-REVIEW.md`. |
| 2D shadow shapes | Four matched slots per family, forced band, rectangle, ellipse and directional-unshaded controls: 48 images. Finite shapes added variety; squared endings could look synthetic. The sample did not establish frequency or shaded small-gauge readability. | Same [2D study](../../../experiments/foreground-context/coherent-study/README.md); local `coherent-shape-screen-gallery/INDEPENDENT-VISUAL-REVIEW.md`. The directional-unshaded control retains other lighting. |
| 3D balanced mixture | 200 candidate and 20 fresh-seed jobs were accepted and their files verified. Recovered jobs used a stricter memory guard and a distinct runtime-dependent identity. The fresh-seed set reused the reference pool. Some scenes had concentrated bright pools, washed targets, strong bar-like shadows or difficult darkness. | [Retry procedure](../../../experiments/blenderproc/studies/balanced-completion-retry/README.md); local `balanced-completion-retry-reviewed/REVIEW.md`, `INDEPENDENT-REVIEW.md`, `verification.json` and `provenance/`. |
| 3D matched lighting | Two 48-image paired screens under forced indoor and outdoor-night conditions. Broader lights and reduced power moderated some highlights but did not remove pools and also darkened already-dim scenes; unconditional fill brightened both dark and bright examples. | [Lighting procedure](../../../experiments/blenderproc/studies/lighting-refinement/README.md); local `lighting-refinement-round1-reviewed/` and `lighting-refinement-round2-reviewed/` reviews and verification. |

The 2D and 3D per-image observations are qualitative and selected; none estimates the frequency of an
artifact in a future distribution. Related compositions and asset reuse limit independence. Inspect
full-size images, mask/geometry matching, actual resolved controls and recorded revisions before using a
finding in a new profile. Failed and partial runs remain identifiable in the local provenance rather than
being counted as successful evidence.

## Cross-engine prototype

The isolated [sample-contract prototype](../../../prototypes/cross_engine_contract/README.md) checks
illustrative records and a small number of native local artifacts. It intentionally distinguishes planar
cropped alpha coverage from 3D binary masks. It does not supply an integrated adapter, shared class map,
version migration or shared scheduling; see [#84](https://github.com/edra-unb-fga/dataset_generator_m1/issues/84).
Missing source identity is represented as unknown, not inferred.

## Review and retention

The 3D collection identifies the original bundle by SHA-256
`aced5844c1a37b545a2bd4d0dec061d97d49382fa1695c12dc6ac953afd276a3` and records hashes for the
original and retry archives in its local review. The retry's identity differs because the resource
policy is part of its study contract. Source, asset and individual image fingerprints live in the
retained provenance; do not replace them with the current branch commit. Some exact historical 2D
drivers exist only in ignored output, although tracked study instructions describe later reproduction
and historical driver hashes. Keep those drivers and pools until a separate retention decision; they are
not guaranteed retrievable from Git alone.

Use [experiment retention](../../EXPERIMENT_RETENTION.md) when selecting compact evidence for version
control. Do not commit raw pools, private input assets or large archives by default. The broader
[roadmap](../../ROADMAP.md) tracks remaining real-data calibration and evaluation.
