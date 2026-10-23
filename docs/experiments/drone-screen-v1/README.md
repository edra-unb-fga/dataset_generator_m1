# Drone scenario screen v1

Initial, environment-local comparison: two warmups and twenty measured fixtures per family, 1280²,
single worker, balanced order, one shared synthesized background per fixture. Landing and landing-pad
compare two baselines plus four naturally sampled scenarios and their forced diagnostic counterparts.
Manometro compares the two generic baselines only. Geometry, sources, masks and annotations were
identical within each fixture. The JSON records profile definitions, environment identity, raw evidence
hashes, activation coverage, paired deltas and slow samples. Rendering ran from the phase-five working
tree above `a8318f2`; its dirty state is explicitly retained, not represented as a clean release.

| Family | current-fast render / modeled seconds | realistic-heavy | daylight candidate | haze candidate | motion candidate | overcast candidate |
| --- | --- | --- | --- | --- | --- | --- |
| landing | .609 / 2.584 | 1.064 / 3.040 | .542 / 2.518 | .553 / 2.527 | .527 / 2.501 | .629 / 2.605 |
| landing-pad | .923 / 3.895 | 1.765 / 4.717 | .780 / 3.730 | .825 / 3.774 | .801 / 3.751 | .913 / 3.862 |
| manometro | .374 / 2.692 | .811 / 3.130 | — | — | — | — |

Modeled production time adds shared synthesis, encoding and writing to rendering, but is **not** a
complete accepted-output throughput benchmark: retries, mask encoding/polygonization and QA are not
all represented. Heavy Gaussian noise on the 2560² background and plasma lighting explain important
slow render cases; `mask_multiband` synthesis explains much of modeled cost. The pad's slowest heavy
render was 5.290 s; its slowest modeled sample was 8.544 s. Do not attribute all of this to one effect.

Visual verdict from synchronized rows and the slowest heavy samples:

- Daylight and motion candidates offer restrained alternatives worth trying on reference imagery.
- Haze is deliberately mild and cannot establish calibrated atmospheric depth.
- Overcast can make dark source ground excessively dark; retain experimental status and user control.
- Heavy profiles remain useful for stronger perturbations. No default or supported effect is removed.
- Sparse naturally activated effects have explicit low-coverage warnings. Forced cases demonstrate
  behavior, not the frequency or average cost of the ordinary mixture.
- Neither attractive pixels nor faster rendering establish better detector accuracy.

Reproduce with `scripts/study_drone_presets.py`; see `docs/DRONE_PRESETS.md`. Reanalysis of existing
raw files uses `scripts/review_drone_studies.py` and does not regenerate images. Full raw bundles and
HTML galleries are ignored under `outputs/experiments/`. The three selected JPEG rows are reviewed
source artifacts. Historical augmentation studies have not been rewritten.

## Material-lighting prototype verdict

Retained branch `codex/prototype-material-lighting`, commit `c6febea`, one-command shell documented
under `prototypes/material_lighting/README.md`. A pinned Ground068 colour/normal/roughness fixture
preserved geometry and masks for all three families. One diagnostic map evaluation took about
0.280 s (normal) or 0.294 s (normal + roughness); these are single observations, not stable benchmarks.
Changes are subtle, foreground illumination remains inconsistent, physical scale is unknown, and there
are no contact shadows. Keep production colour mapping; defer PBR/shading until a coherent scene-light
model and stronger reference evidence justify it. Do not merge the prototype shell.
