# Dataset Generator M1

Auditable synthetic YOLO generation for the `landing` and `manometro` families. The generator uses deterministic scene plans, one shared foreground/background homography, mask-derived boxes, versioned background-mixing recipes, resumable pools, Rich live analytics, and deterministic process workers.

## Install

```powershell
uv sync --extra dev
```

## Workflow

Validate the complete composer, profile catalog, mappings, transforms, hashes, and recipe DAGs:

```powershell
uv run python -m dataset_generator_m1 validate --config examples/configs/landing_minimal.yaml
```

Discover profiles or inspect the exact resolved contract:

```powershell
uv run python -m dataset_generator_m1 catalog list
uv run python -m dataset_generator_m1 catalog show builtin:appearance/realistic-heavy
uv run python -m dataset_generator_m1 resolve --config examples/configs/landing_minimal.yaml
```

Review warnings, disk use, and an environment-local ETA before generation:

```powershell
uv run python -m dataset_generator_m1 preflight --config examples/configs/landing_minimal.yaml --output-dir outputs/landing-expA --workers auto
```

Preview background recipes or compare named variants before committing to a run:

```powershell
uv run python -m dataset_generator_m1 preview backgrounds --config examples/configs/landing_minimal.yaml --samples-per-recipe 4 --output-dir outputs/background-preview
uv run python -m dataset_generator_m1 preview scenes --config examples/configs/landing_minimal.yaml --variants examples/configs/landing_variants.yaml --samples 8 --output-dir outputs/scene-preview
```

Generate or resume a pool:

```powershell
uv run python -m dataset_generator_m1 generate --config examples/configs/landing_minimal.yaml --num-images 50 --output-dir outputs/landing-expA --workers auto --qa-samples 12
uv run python -m dataset_generator_m1 generate --config examples/configs/landing_minimal.yaml --num-images 50 --output-dir outputs/landing-expA --workers auto --resume
```

Inspect and control a live run from another terminal:

```powershell
uv run python -m dataset_generator_m1 run status outputs/landing-expA
uv run python -m dataset_generator_m1 run pause outputs/landing-expA
uv run python -m dataset_generator_m1 run continue outputs/landing-expA
uv run python -m dataset_generator_m1 run stop outputs/landing-expA
```

The live/full terminal display also accepts `p` for pause/continue and `s` for graceful stop. See
[docs/RUN_CONTROL.md](docs/RUN_CONTROL.md) for checkpoint, resume, audit-log, and ETA semantics.

Benchmark, compare, and export:

```powershell
uv run python -m dataset_generator_m1 benchmark --config examples/configs/landing_minimal.yaml --output-dir outputs/bench-A
uv run python -m dataset_generator_m1 compare --left outputs/bench-A --right outputs/bench-B --output-dir outputs/bench-comparison
uv run python -m dataset_generator_m1 export --pool outputs/landing-expA --format yolo --strategy asset-disjoint --splits train=0.8,val=0.1,test=0.1 --output-dir outputs/landing-yolo
```

Run a paired heavy-augmentation study or generate with the reviewed standard appearance:

```powershell
uv run python -m dataset_generator_m1 experiment augmentations --config examples/configs/landing_minimal.yaml --output-dir outputs/experiments/landing-heavy
uv run python -m dataset_generator_m1 generate --config examples/configs/landing_minimal.yaml --num-images 20 --output-dir outputs/landing-realistic-heavy
```

`realistic-heavy` is the shipped default. To use `current-fast`, copy a composer and change
`appearance.preset` to `builtin:appearance/current-fast`; the choice remains visible and versionable.

Every command supports `--display auto|live|full|plain|quiet` and `--output-format human|json`. JSON mode produces one machine-readable result document. Rich follows standard terminal detection and `NO_COLOR`.

## Pool artifacts

Generation writes `run.json`, `samples.jsonl`, `rejections.jsonl`, `metrics.jsonl`, `summary.json`, atomic images, and a small `qa/index.html` gallery. Resume requires the same resolved contract and asset-catalog fingerprint.

See [CONTEXT.md](CONTEXT.md) for the domain language, [docs/SPEC.md](docs/SPEC.md) for the normative
contract, [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for contribution and verification rules,
[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for paired-study rules,
[docs/APPEARANCE_EFFECTS.md](docs/APPEARANCE_EFFECTS.md) for the supported effect catalog, and
[docs/PREFLIGHT.md](docs/PREFLIGHT.md) for ETA evidence and warning receipts, and
[docs/ROADMAP.md](docs/ROADMAP.md)
for measured follow-on work.
