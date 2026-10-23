# Source isolation before generation

Run feasibility analysis on an unpartitioned composer before creating a large pool:

```powershell
uv run python -m dataset_generator_m1 partition --config examples/configs/landing-pad_minimal.yaml --policy background-disjoint --splits train=0.8,val=0.1,test=0.1 --output-file configs/local/pad-partitions.json --output-format json
```

The manifest contains source-content assignments, known material groups, class/background support,
shared foreground identities and a digest. No images or generation pools are created. An infeasible
report is useful evidence, not permission to claim a valid split. Check each requested split's support.

Use the same source roots and add this to each split's composer (paths are relative to the composer):

```yaml
inline:
  assets:
    backgrounds: {paths: [backgrounds], recursive: true}
    foregrounds: {paths: [foregrounds/landing_pad_foregrounds], recursive: true}
    partition: {manifest_file: pad-partitions.json, split: train}
```

Generate one pool per split. Repeat with `split: val` and `split: test`, then export all pools using
`--strategy background-disjoint` and the same `--splits`. Export validates actual sample lineage and
preserves declared assignments. Modified source catalogs require a new reviewed manifest.

`asset-disjoint` isolates foreground and background content. `background-disjoint` deliberately allows
the known pad artwork in every split while keeping backgrounds/materials isolated. This tests new
ground appearances, not unseen marker designs. Known derivatives share a `material_id` in background
catalog metadata; identical hashes also join groups. Unknown derivatives cannot be inferred reliably.

Source support is not a promise of exact image counts, recipe feasibility or real-world model quality.
