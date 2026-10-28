# Controlled Experiments

Experiments are read-only analyses of the production pipeline. Their job is to isolate a decision,
preserve paired inputs, and make evidence inspectable—not to create a second renderer.

## Generation-profile tradeoffs

The [profile comparison](experiments/profile-tradeoffs-v1/README.md) covers maintained foreground tasks,
natural and forced appearance, heavy-stage ablations, recipe operation costs, resolution and repeated
accepted-output throughput. It introduces experimental camera presets and an explicit content-changing
direct-dominant background mixture; existing defaults remain unchanged. Generic RGBA label/wrench
fixtures verify the shared flat renderer while documenting family-registration and YOLO-hole limits.

Reproduce with `scripts/study_profile_tradeoffs.py`, `scripts/study_background_costs.py` and
`scripts/benchmark_profile_composers.py`. Keep raw pools and report apps under ignored
`outputs/experiments/`; only compact measurements and selected paired sheets are retained here.

## Augmentation attribution

Run the default paired study:

```powershell
uv run python -m dataset_generator_m1 experiment augmentations `
  --config examples/configs/landing_minimal.yaml `
  --output-dir outputs/experiments/landing-heavy
```

Use `--warmups`, `--samples`, and `--include-stress` deliberately. A custom `--matrix` is strict and
may change only the three appearance stages. Geometry, source assets, recipes, sampling, and output
dimensions remain paired.

The default treatments are `no-appearance`, `current`, `legacy-heavy-compatible`, three isolated
realistic-heavy stages, and `realistic-heavy-combined`. The legacy treatment is diagnostic and maps
unsupported `AtmosphericFog` to `RandomFog`; this approximation is disclosed in every report.
`all-effects-stress` is benchmark-only. Normal generation never selects either profile implicitly.
Visual review rejected `RandomFog` for the realistic preset because even low-density settings softened
the complete frame and obscured labels. Realistic weather uses light drizzle instead; fog remains only
in the disclosed legacy-compatible and stress treatments.

That paragraph describes the historical default study, not the current effect catalog. The reviewed
[native fog comparison](experiments/native-fog-v1/README.md) keeps all three depth-dependent
`AtmosphericFog` modes and patch-based `RandomFog` available as distinct effects. It supplies paired
timing evidence for preflight warnings while leaving the earlier approximation record unchanged.

The reviewed realistic-heavy treatment is now the shipped composer default:

```powershell
uv run python -m dataset_generator_m1 generate `
  --config examples/configs/landing_minimal.yaml `
  --num-images 20 `
  --output-dir outputs/landing-realistic-heavy
```

The report's `current` treatment retains its historical meaning and resolves
`builtin:appearance/current-fast` explicitly.

## Interpretation rules

- Causal performance conclusions apply only to paired treatments in the same environment.
- Use render-only cost to identify appearance work and modeled production cost to include the shared
  synthesis, encode, and write work a normal sample would incur.
- Inclusive scene-render duration is not the sum of nested spans. Effect traces are exclusive calls.
- Compare per-call, per-object, and per-megapixel values before generalizing.
- Fewer than 20 measured fixtures produces a low-sample warning.
- Do not establish cross-machine thresholds until hardware classes have reviewed baselines.

Raw bundles under `outputs/experiments/` are ignored. A reviewed study may promote only its definition,
compact conclusions, environment/profile fingerprints, and a small contact sheet into `docs/experiments/`.

## Report layout verdict

The retained `codex/prototype-augmentation-report` branch compares three image-first layouts. The
synchronized contact-sheet design is the production default because it keeps the causal pair visible.
Slow-sample navigation, stage tabs, and difference views remain secondary investigation tools.

The reviewed landing/manometro conclusion, compact measurements, environment fingerprints, and selected
visual evidence are stored in [`docs/experiments/augmentation-heavy-v1/`](experiments/augmentation-heavy-v1/).
Native-fog conclusions and the selected comparison sheet are stored in
[`docs/experiments/native-fog-v1/`](experiments/native-fog-v1/).
Raw study bundles remain ignored under `outputs/experiments/`.

## Placement rejection diagnostics

Run the production-path landing study:

```powershell
uv run python -m dataset_generator_m1 experiment placement `
  --config examples/configs/landing_minimal.yaml `
  --samples 200 `
  --qa-samples 20 `
  --output-dir outputs/experiments/landing-placement
```

The pool stores bounded object-attempt evidence. The study adds spatial heatmaps and failed-plan
overlays without changing the planner. Interpret rates with their attempt denominators; shares of all
rejections are not conditional rejection rates. Raw output remains ignored. Reviewed conclusions and
one compact contact sheet may be promoted under `docs/experiments/`.

## Asset-disjoint feasibility

Analyze a validated pool without creating an export tree:

```powershell
uv run python -m dataset_generator_m1 export `
  --pool outputs/pool-a `
  --strategy asset-disjoint `
  --splits train=0.8,val=0.1,test=0.1 `
  --analyze-only `
  --output-format json
```

The reviewed [landing/manometro study](experiments/asset-disjoint-v1/README.md) compares current hash,
greedy sample-balance, and greedy class-balance assignments. It found connectivity—not allocator
choice—to be the limiting factor. Raw study pools remain ignored.

## Process-tree telemetry overhead

The reviewed [three-pair study](experiments/process-tree-overhead-v1/README.md) compares continuous
one-second process-tree monitoring with the explicit `off` policy using fixed 20-sample landing runs.
Paired generated content remained identical and no resource samples were dropped. The timing range was
too variable to establish a universal overhead budget; interpret it only as local evidence.

## Shared planar illumination, wear and occlusion

The [round-one evidence](experiments/planar-surfaces-v1/README.md) isolates lighting, wear and capture effects on20 paired fixtures per natural/forced treatment (+2 warmups), then compares four selected production configurations in3 rotating-order repetitions of20 accepted images (+2 warmups). Appearance-only mask/box/content invariants stay strict; occlusion deliberately changes annotations. `scripts/study_planar_surfaces.py` reproduces the study, and `scripts/report_planar_surfaces.py` adds static Matplotlib charts/offline HTML without adding a generation dependency.

Background synthesis dominates this host's measured total cost; scene lighting, source-local wear and procedural raster layers add distinct work. Keep defaults unchanged. Bounded optimizations and hardware-class promotion require additional evidence. Current procedural occluders are geometry fixtures, not demonstrated photographic realism. Real references/predictions remain missing; use `BLENDERPROC_COMPARISON.md` for the future matched-engine protocol.

## Background performance and execution controls

The [round-two report](experiments/background-performance-v1/README.md) measures recipe hotspots,
existing cache/thread/worker/queue controls, and interleaved original/optimized production runs.
Redundant float copies, expired DAG arrays, materialized multiband intermediates and duplicate polygon
projections were removed with exact output/evidence checks. Three repetitions of20 accepted images
(+2 warmups) per case show local median paired throughput gains of7.7–10.8%; the two-worker range
includes a slower optimized repetition. Sampled process memory also fell. These are one-host results,
not generic default recommendations or real-model quality evidence.

Native threading helped here; the256 MiB decoded cache did not, despite recorded hits. Defaults stay
unchanged. Large Gaussian smoothing remains the dominant recipe cost; approximation/fidelity changes
or a scheduling/transport redesign require the next planning decision. Reproduce with
`scripts/study_background_optimizations.py`, `scripts/study_execution_controls.py`,
`scripts/probe_multiband_allocations.py` and the optional Matplotlib authoring script
`scripts/report_background_performance.py`. Raw evidence remains ignored. #28 still needs additional
hardware-class evidence.

The follow-up [worker/thread scaling report](experiments/worker-scaling-v1/README.md) tests6 workers
with24 requested OpenCV threads each and compares1×24,2×12,4×6,6×1,6×4 and6×24 over3 repetitions
of24 accepted images (+2 warmups). Six single-threaded workers led this host's measurements; all
encoded images and mask/annotation signatures match. A lower experimental watchdog protects current
host headroom. The accompanying conservative RAM accounting is evaluated separately against observed
process-tree memory; it does not fit the planner to this host's fastest policy. See `WORKER_SCALING.md`
for scope, safeguards and remaining limits.

The [high-worker follow-up](experiments/high-workers-v1/README.md) records a12-worker capacity stop
and the deliberate16/24-worker skips after the available-memory floor was reached. Repeated6×1/6×2
cases use48 samples (+2 warmups), with exact output signatures. Independent traced recipe allocations
validate the replacement phase/lifetime RAM model: it counts live DAG arrays and a maximum worker
phase instead of summing expired values and mutually exclusive phases. RSS predictions remain
distinct from Linux PSS/USS physical/private observations. `scripts/probe_background_memory.py` and
`scripts/report_high_workers.py` reproduce the allocation/report evidence; source and model hashes
are retained. Capacity decisions depend on current host headroom, not CI latency thresholds.

The subsequent [twelve-worker retry](experiments/twelve-worker-retry-v1/README.md) lowers the available
host-memory floor to 1.5 GiB. A single 12-image run completes with exact signatures matching the earlier
six-worker short controls, but the 48-image attempt crosses the revised floor during its second batch.
The report retains both memory timelines and explicitly distinguishes short completion from an
unfinished sustained comparison. No runtime code, estimator or generic defaults changed.

The [3–6 worker tuning study](experiments/execution-tuning-v1/README.md) screens one/two-thread cases,
then confirms single-threaded 3/4/5/6-worker policies over three 48-image repetitions. It introduces
portable capacity candidates and evidence-bound local recommendations without promoting a hardware-
class speed default. Five workers is the local 5%-tolerance choice; six has the highest measured median.


## Optional physical material, lighting and camera pilot

The [BlenderProc pilot](experiments/blender-pilot-v1/README.md) compares nominal plastic panels over
three hash-pinned CC0 PBR grounds and two HDR environments, with paired day/night, roughness, UV,
shadow, haze, DOF, camera-motion and distortion treatments. Geometric full/visible masks remain sharp
at the reference pose. Canonical COCO/evaluator preparation is required; bounded optional YOLO output
retains polygon fidelity. `scripts/blenderproc_pilot.py` runs the isolated workflow and
`scripts/report_blender_comparison.py` authors compact portable evidence. Raw assets and study pools
stay ignored. The sparse feature study cannot establish detector transfer or universal engine speed;
`BLENDERPROC_COMPARISON.md` retains the later repeated/equal-budget real-evaluation protocol.


The [Blender execution follow-up](experiments/blender-execution-v1/README.md) retains the Colab T4
native-GPU-denoising findings, the source/input-bundle qualification and paired initialization evidence.
`scripts/study_blender_execution.py` reads saved matrices for alternating-order trials and exact mask
checks. Hardware policies remain explicit data; low-sample denoising probes and repeated initialization
studies retain distinct scopes and throughput denominators.


## Shared surface integration study

The [surface integration evidence](experiments/surface-integration-v1/README.md) follows
[round three](REALISM_ROUND_THREE.md). `scripts/study_surface_2d.py` runs production paired pools;
`scripts/study_surface_integration.py` runs saved physical cue/qualification cells under a single
conservative budget ledger. `scripts/study_surface_performance.py` separates warmups from measured
whole-command throughput, rotates pristine/wear order and checks exact within-engine mask/geometry
invariants. Resolved hardware profiles remain saved data. Source/input/controller fingerprints and
all probe/render/warmup/retry costs accompany the measurements; local setup/export costs have separate
denominators. No measured CPU/GPU ratio is a causal engine speed ratio across these hosts.

`scripts/report_surface_integration.py` builds the visual report from retained evidence. Raw pools,
assets, portable archives and application intermediates stay ignored. The tracked compact evidence,
selected review figures and standalone HTML intentionally retain synthetic examples only. Reserved
scene combinations are reviewed once after development selection; real references and trained-model
outcomes remain absent rather than inferred from visual preference.


## Camera and environment engineering screen

See [round four](REALISM_ROUND_FOUR.md) and its [partial visual report](experiments/camera-environments-v1/README.md).
`scripts/study_camera_environments.py` consumes a saved paired matrix and resource-guarded optional
Blender runs; `scripts/study_linear_compositing.py` compares paired 2D visual fixtures, and
`scripts/study_linear_compositing_timing.py` defines a separate guarded timing study. Completed-cell
archives are hash-verified and packaged between timed cells. The initial 2D screen preserved mask and
annotation evidence; earlier plain-wall 3D samples were reviewed as prototypes. Two subsequent
3D attempts hit the existing system swap-out guard; the final 3D visual and performance checks were
not completed. Do not treat the aborted run or single smoke renders as a throughput comparison.


## Quick L4 and T4 execution screen

The [Colab GPU screen](experiments/colab-quick-screen-v1/README.md) compares small matched camera
scenes on L4 and T4 with saved, explicitly experimental worker policies. It records observed resource
use, compute-unit rates, exact within-resolution mask checks and the excluded overlapping-transfer
screen. Four measured scenes per setting cannot establish a hardware-class default or realism.

The exploratory [L4 worker/thread screen](experiments/l4-worker-scaling-v1/README.md) records paired 640² and 1280² outputs, an eight-worker case, separate system RAM and GPU memory guards, sampled utilization and automatic shutdown evidence. Its short cases do not justify a general hardware default.
