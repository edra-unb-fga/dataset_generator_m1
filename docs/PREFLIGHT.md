# Preflight, ETA, and Warning Receipts

Preflight resolves one immutable composer contract and answers three separate questions before a run creates its output directory:

1. Is the configuration valid and compatible?
2. Is there enough estimated disk capacity?
3. What environment-local runtime range and performance warnings are supported by current evidence?

```powershell
uv run python -m dataset_generator_m1 preflight `
  --config examples/configs/landing_minimal.yaml `
  --output-dir outputs/landing-run `
  --workers 4
```

Runtime is always a range with a confidence label. The initial estimate combines versioned paired-study knowledge, image megapixels, run size, family, and worker count. Matching observations in ignored `.cache/performance-observations.jsonl` may improve later estimates. Local observations never rewrite tracked profile metadata.

When a profile is novel, weakly evidenced, or marked as confirmation-risk, preflight runs one disposable warm-up and up to three measured candidates through the production render path. The probe does not create the requested output directory. Its accepted and rejected candidate durations are retained only in the local observation cache.

## Warnings and receipts

Invalid schemas, missing assets, incompatible profiles, and insufficient disk remain hard failures. Slow but valid effects remain available.

`realistic-heavy` emits informational cost context and needs no recurring acknowledgement. Legacy, stress, RandomFog-heavy, and undocumented confirmation-risk stacks require a receipt bound to the exact:

- resolved contract hash;
- image count and dimensions;
- worker count;
- required warning codes and evidence version;
- environment class.

For an explicit preflight review, write a receipt after reading the result:

```powershell
uv run python -m dataset_generator_m1 preflight `
  --config examples/configs/my-random-fog.yaml `
  --output-dir outputs/random-fog-run `
  --workers 2 `
  --write-receipt .cache/receipts/random-fog-run.json
```

Human-mode `generate` can show and confirm the same warnings interactively, then writes a hashed receipt under `.cache/preflight-receipts/`. Quiet and JSON generation never prompt and must receive `--receipt PATH`. There is deliberately no blanket `--accept-warnings` switch. Any relevant contract, count, dimensions, workers, evidence, or environment change invalidates the receipt.

Advanced inline effects remain available. An inline stack is disclosed as unreviewed; adding patch-based
`RandomFog` makes its known high and variable cost acknowledgement-required. Reviewed reusable bundles carry
their own curated metadata instead. Local observations may refine ETA but never rewrite tracked warnings.

Preflight estimates are planning aids, not cross-machine performance guarantees. The live run ETA will recalibrate from actual accepted and rejected candidates while excluding paused time.
