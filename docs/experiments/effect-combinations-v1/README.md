# Paired effects comparison

Eight synthetic landing-pad scenes were generated locally under nine 2D configurations. Geometry, annotations and mask signatures match across the variants. The controls use premultiplied alpha filtering; isolated enabled effects and the `all` cell are forced on at sampled strengths, while `all-capture` samples probabilities as well as adding camera effects. Its difference from `all` therefore does not isolate capture alone. All scenes reuse the available synthetic asset catalog. No real images or trained models were evaluated.

| Variant | Mean absolute RGB change on targets (0–255) | Change outside target masks (0–255) |
|---|---:|---:|
| Wear | 5.82 | 0.01 |
| Shared lighting | 1.82 | 2.13 |
| Environmental shade | 1.23 | 1.94 |
| Foreground context | 10.02 | 0.01 |
| Wear + lighting | 5.94 | 2.13 |
| Wear + context | 12.02 | 0.02 |
| All forced | 11.46 | 3.61 |
| All with sampled capture | 9.68 | 2.83 |

These are averaged over eight selected paired scenes and decoded JPEGs, using baseline visible masks. They describe visual magnitude, not realism, statistical significance, causal model impact or detector usefulness. The per-scene report contains exact crops, activation traces and masks. Shade's target changes ranged from essentially zero to 3.42 despite forced activation; a field can miss a target.

Independent visual inspection found that wear and context were the most conspicuous individual changes in these examples. Moderate wear sometimes formed soft spots that looked more like stains than abrasion. Context altered target colors without adding contact cues. Lighting and shade were usually subtle in target crops but also affected the background. All combinations left some pads looking like sharply bounded graphics on the ground. These are qualitative judgments on small synthetic samples.

The locally guarded run completed all 72 images with no new host swap-out, a peak summed process-tree RSS of 884,105,216 bytes and at least 7,372,877,824 bytes of available host memory. The initial sanity attempt failed on missing preflight acknowledgement before generation; its corrected guarded rerun and the full run succeeded. A separate Colab CPU attempt used the pre-fix bundle, failed on the same preflight issue, returned logs, and stopped; it produced no images. The previous local host-wide swap guard stop was not an OOM.

Study definitions, controls and reproduction instructions are in [`experiments/effect-combinations/README.md`](../../../experiments/effect-combinations/README.md). Raw images and the filterable HTML remain in ignored experiment outputs. 3D attempts are tracked independently: an initial larger L4 run timed out without a retrieved archive, and a smaller retry identified a relative reference-pool path error; both runtimes stopped. Do not interpret these failures as physical-render results.

## Physical retry and historical check

The corrected L4 retry completed five paired cells (baseline, moderate wear, glossy roughness 0.25, overcast lighting, and wear + glossy + overcast), using three scene intents and one deliberately close diagnostic view: 20 accepted renders. All full and visible masks matched the baseline for all four jobs in each cell. The prior larger timeout and wrong-reference-path attempt remain recorded as failures, not as completed studies. The corrected archive was verified and the runtime confirmed stopped; generated wear-map files were omitted from the compact archive, but the sealed input, definitions, identities, image results, masks and per-cell checkpoints are retained.

Mean absolute RGB changes on target pixels, relative to baseline, were 3.04 for wear, 8.14 for glossy, 16.41 for overcast and 15.98 for the combined treatment (0–255 levels, four matched jobs; background values and per-image breakdowns are in the report). These numbers measure change, not realism or detector relevance. The wear maps alter albedo, roughness and bump together. On visual review moderate wear was often faint and looked like soft discoloration; the glossy condition mostly changed blue appearance without a clearly localized highlight, while overcast changed background and target together. The combined result preserved those changes but did not clearly solve the flat pad-to-ground contact appearance. The tiny shared-asset sample is insufficient to generalize.

A separate local historical check generated four naturally sampled `landing` examples from September 13, 2026 commit `d4079f9` and the current worktree, using the same seeds, old marker assets and `realistic-heavy` configuration. All four geometry signatures and decoded images matched exactly in this environment. Four current landing-pad examples were generated separately for visual context; the pad did not exist in the historical version and differs in subject, count and placement, so it is not a controlled old-pad comparison. The `realistic-heavy`, `current-fast`, standard scene and standard background-mixing profile files were identical between that old snapshot and current main. Four matching cases do not rule out regressions for other seeds, settings, or families. All three runs completed under one-worker host memory/swap safeguards.
