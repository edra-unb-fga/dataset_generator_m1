# Dataset Generator M1

Auditable synthetic YOLO generation for the `landing` and `manometro` families. The generator uses deterministic scene plans, one shared foreground/background homography, mask-derived boxes, versioned background-mixing recipes, resumable pools, Rich live analytics, and deterministic process workers.

## Install

```powershell
uv sync --extra dev
```

## Workflow

Validate the complete profile, catalog, mappings, transforms, hashes, and recipe DAGs:

```powershell
uv run python -m dataset_generator_m1 validate --config examples/configs/landing_minimal.yaml
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

Benchmark, compare, and export:

```powershell
uv run python -m dataset_generator_m1 benchmark --config examples/configs/landing_minimal.yaml --output-dir outputs/bench-A
uv run python -m dataset_generator_m1 compare --left outputs/bench-A --right outputs/bench-B --output-dir outputs/bench-comparison
uv run python -m dataset_generator_m1 export --pool outputs/landing-expA --format yolo --strategy asset-disjoint --splits train=0.8,val=0.1,test=0.1 --output-dir outputs/landing-yolo
```

Run a paired heavy-augmentation study, or explicitly opt a normal generation run into the reviewed
realistic-heavy appearance preset:

```powershell
uv run python -m dataset_generator_m1 experiment augmentations --config examples/configs/landing_minimal.yaml --output-dir outputs/experiments/landing-heavy
uv run python -m dataset_generator_m1 generate --config examples/configs/landing_minimal.yaml --appearance-preset realistic-heavy --num-images 20 --output-dir outputs/landing-realistic-heavy
```

Every command supports `--display auto|live|full|plain|quiet` and `--output-format human|json`. JSON mode produces one machine-readable result document. Rich follows standard terminal detection and `NO_COLOR`.

## Pool artifacts

Generation writes `run.json`, `samples.jsonl`, `rejections.jsonl`, `metrics.jsonl`, `summary.json`, atomic images, and a small `qa/index.html` gallery. Resume requires the same resolved contract and asset-catalog fingerprint.

See [CONTEXT.md](CONTEXT.md) for the domain language, [docs/SPEC.md](docs/SPEC.md) for the normative
contract, [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for contribution and verification rules,
[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for paired-study rules, and [docs/ROADMAP.md](docs/ROADMAP.md)
for measured follow-on work.
