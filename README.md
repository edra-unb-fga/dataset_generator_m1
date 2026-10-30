# Dataset Generator M1

Auditable synthetic YOLO generation for the `landing`, `landing-pad`, and `manometro` families.
`landing-pad` generates complete rectangular panels using the shared planar renderer; its shipped
blue/yellow pads come from the supplied takeoff and landing SVG artwork. Use a foreground-root override
to supply other artwork. See [the delivery contract](docs/PRACTICAL_WORKFLOW.md) for count-policy and
split semantics.

The generator uses deterministic scene plans, one shared foreground/background homography,
alpha-evidence-derived annotations, versioned background-mixing recipes, resumable pools, Rich live
analytics, and deterministic process workers.

The [first-use review](docs/experiments/first-use-review-v1.md) records tested CLI journeys and remaining
usability gaps. The optional [BlenderProc harness](experiments/blenderproc/README.md) has separate CPU
and GPU preparation instructions.

Opt-in [planar surface examples](docs/SURFACE_RENDERING.md) add shared illumination, local wear and procedural occlusion.
[Offline evaluation and reference checks](docs/EVALUATION.md) consume supplied predictions/camera inputs.
The [round-one report](docs/experiments/planar-surfaces-v1/README.md) separates synthetic correctness, visual limits and generation cost.

## Find your starting point

- Use the workflow below for the shipped 2D generator; the annotation family describes the target
  and annotation rules, while a scene preset describes its visual context. See [scene presets](docs/SCENE_PRESETS.md).
- Browse [study evidence](docs/experiments/README.md) by question, or read the [retention guide](docs/EXPERIMENT_RETENTION.md) before handling raw runs.
- The [optional BlenderProc harness](experiments/blenderproc/README.md) is separate experimental 3D work; real-image calibration and model-transfer evidence remain open.

## Install

Run these commands from the repository root. The one-line commands below work in Bash and PowerShell;
commands in other guides marked `powershell` may use PowerShell-specific continuation syntax.

```powershell
uv sync --extra dev
```

## Workflow

For an interactive end-to-end journey, start here:

```powershell
uv run python -m dataset_generator_m1 start
uv run python -m dataset_generator_m1 start --config configs/my-landing.yaml
```

`start` discovers saved composers and shipped examples, edits essentials before advanced subjects, saves
the composer, prepares the exact run once, asks for a mandatory final confirmation, displays live controls,
and ends on a persistent QA/audit/export dashboard. It is interactive-only; all atomic commands below remain
stable for scripts and expert use.

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

Create a versionable composer with the guided Rich cockpit:

```powershell
uv run python -m dataset_generator_m1 configure --family landing --output configs/local/my-landing.yaml
```

The cockpit starts from `realistic-heavy`, shows warnings and an ETA range, and supports reviewed profile
choices plus a stage-by-stage advanced effect builder. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

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
uv run python -m dataset_generator_m1 run inspect outputs/landing-expA
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
uv run python -m dataset_generator_m1 export --pool outputs/landing-expA --strategy asset-disjoint --splits train=0.8,val=0.1,test=0.1 --analyze-only --output-format json
uv run python -m dataset_generator_m1 export --pool outputs/landing-expA --format yolo --strategy asset-disjoint --splits train=0.8,val=0.1,test=0.1 --output-dir outputs/landing-yolo
uv run python -m dataset_generator_m1 export --pool outputs/landing-expA --format yolo --task segmentation --mask-semantics family --output-dir outputs/landing-yolo-segmentation
```

For a one-image smoke test, use `--strategy random --splits train=1` on the export command: a
train/validation/test split cannot give each subset a sample from a single image. Each YOLO export
contains `data.yaml`, image and label directories, and `export.json`. Generated pools and exports go to
the output directories you provide; generation may also record an ignored machine-local performance
observation under `.cache/` for future estimates.

Analyze-only validates the source pool and explains connected components, class support, achievable
balance, and deterministic strategy comparisons without creating an export directory. Actual
asset-disjoint exports preserve the hash policy and embed the same analysis in `export.json`.

Run a paired heavy-augmentation study or generate with the reviewed standard appearance:

```powershell
uv run python -m dataset_generator_m1 experiment augmentations --config examples/configs/landing_minimal.yaml --output-dir outputs/experiments/landing-heavy
uv run python -m dataset_generator_m1 generate --config examples/configs/landing_minimal.yaml --num-images 20 --output-dir outputs/landing-realistic-heavy
```

`realistic-heavy` is the shipped default. To use `current-fast`, copy a composer and change
`appearance.preset` to `builtin:appearance/current-fast`; the choice remains visible and versionable.

The experimental `camera-minimal` and `camera-balanced` presets offer restrained final-image camera
variation. Try `examples/configs/landing-pad_camera-minimal.yaml`, or the explicit content-changing
`landing-pad_direct-camera.yaml`. The [profile tradeoff study](docs/experiments/profile-tradeoffs-v1/README.md)
compares visuals, per-stage cost, background mixtures and full generation without changing defaults.

Override files and typed leaves compose without changing code:

```powershell
uv run python -m dataset_generator_m1 resolve --config examples/configs/landing_minimal.yaml --overrides experiments/run-overrides.yaml --set run.num_images=200 --set execution.workers=4
```

Every command supports `--display auto|live|full|plain|quiet` and `--output-format human|json`. JSON mode produces one machine-readable result document. Rich follows standard terminal detection and `NO_COLOR`.

## Pool artifacts

The experimental [drone scenario screen](docs/experiments/drone-screen-v1/README.md) compares natural
and forced effects without changing defaults. [Pinned materials and planar UV mapping](docs/MATERIALS.md)
support offline reuse and keep colour maps separate from normal/roughness data. Use `materials --help`
and `catalog show builtin:appearance/drone-daylight-candidate` to explore them.

Generation writes `run.json`, `samples.jsonl`, `rejections.jsonl`, `metrics.jsonl`, `summary.json`, atomic images, exact cropped-alpha mask archives, and a small `qa/index.html` gallery. Detection export remains the default; pool-v2 also supports YOLO instance segmentation without rerendering. See [docs/SEGMENTATION.md](docs/SEGMENTATION.md). Resume requires the same resolved contract and asset-catalog fingerprint.

See [CONTEXT.md](CONTEXT.md) for the domain language, [docs/SPEC.md](docs/SPEC.md) for the normative
contract, [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for contribution and verification rules,
[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for paired-study rules,
[docs/APPEARANCE_EFFECTS.md](docs/APPEARANCE_EFFECTS.md) for the supported effect catalog, and
[docs/PREFLIGHT.md](docs/PREFLIGHT.md) for ETA evidence and warning receipts,
[docs/CONFIGURATION.md](docs/CONFIGURATION.md) for composer authoring and overrides, and
[docs/ROADMAP.md](docs/ROADMAP.md)
for measured follow-on work.

For a new computer or a different CPU/RAM budget, follow [execution and benchmark guidance](docs/EXECUTION.md).
Local tuning stays under ignored `configs/local/` and `.cache/`; generation does not silently lower
quality to satisfy hardware budgets.
