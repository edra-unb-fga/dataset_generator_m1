# Asset-disjoint feasibility v1

Two fixed `current-fast` pools were generated with 200 samples each, then analyzed with requested
`train=0.8,val=0.1,test=0.1` splits. Raw pools remain ignored. The analysis treated every foreground
and synthesized-background source as a strict disjointness constraint.

## Landing

- All 200 samples formed one source-connected component.
- Hash assignment placed the component in `val` (`0/200/0`), with L1 fractional deviation `1.8`.
- Greedy sample/class assignment placed it in `train` (`200/0/0`), with L1 deviation `0.4`.
- Every class had only one component of support, so no class can occur in multiple strict splits.

## Manometro

- Nine components existed, but the largest contained 190/200 samples (95%).
- Hash assignment produced `8/2/190`, with L1 fractional deviation `1.7`.
- Both greedy comparisons produced `190/0/10`, with L1 deviation `0.3`.
- Classes `40-60` and `60-80` had fewer supporting components than requested splits.

## Decision

Keep the current hash assignment as the production policy and expose the structural warnings in both
analyze-only and actual exports. Greedy assignment cannot solve connectivity.

The appropriate follow-up is to investigate source/catalog partitioning before generation, possibly
with split-specific background and foreground catalogs. That is a new generation contract, not an
exporter tuning. No exact quota or default policy change is made here.
