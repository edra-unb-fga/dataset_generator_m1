# Dataset Generator M1 Normative Specification

Composer schema v2 is a clean generation break. Earlier pools remain readable for audit, comparison,
and export, but cannot be resumed. `CONTEXT.md` defines canonical terminology.

## 1. Public commands

The stable command surface is:

```text
start [--config COMPOSER]
catalog list
catalog show PROFILE-REFERENCE [--config COMPOSER]
catalog promote --config COMPOSER --stage background|foreground|final --id ID
configure --family landing|manometro --output COMPOSER
resolve --config COMPOSER [--overrides FILE] [--set PATH=VALUE...]
validate --config COMPOSER
preview scenes --config COMPOSER [--variants VARIANTS] --samples N --output-dir DIR
preview backgrounds --config COMPOSER --samples-per-recipe N --output-dir DIR
generate --config COMPOSER [--num-images N] --output-dir DIR [--resume] [--workers auto|N] [--qa-samples N]
run status|inspect|pause|continue|stop OUTPUT_DIR
experiment augmentations --config COMPOSER --output-dir DIR [--matrix MATRIX] [--warmups N] [--samples N] [--include-stress]
experiment placement --config COMPOSER --samples N --qa-samples N --output-dir DIR
benchmark --config COMPOSER --output-dir DIR [--samples N] [--warmup N]
compare --left ARTIFACT --right ARTIFACT --output-dir DIR
export --pool DIR [--pool DIR...] --format yolo --strategy random|stratified|asset-disjoint --splits ... [--analyze-only] [--output-dir DIR]
```

`start` is an interactive orchestration interface over the same atomic contracts. It discovers composers,
saves edits, prepares once, requires final approval, delegates generation, and renders persistent results.
It refuses non-TTY use with equivalent atomic-command guidance.

Every atomic leaf command accepts `--display auto|live|full|plain|quiet` and `--output-format human|json`. `auto` selects a full-screen Rich display for sufficiently large interactive terminals, an inline Live display for smaller terminals, and plain output otherwise. JSON disables generation display and emits exactly one versioned result or error document. Rich follows normal terminal and `NO_COLOR` behavior.

`num_images`, `qa_samples`, and `execution.workers` are ordinary declared leaf overrides. `realistic-heavy` is the shipped
appearance default and participates in the resolved contract hash.
Scene previews use named variant YAML overlays. Augmentation matrix files are strict appearance-only
contracts and fail before artifacts are created if they attempt to change geometry or sources.

## 2. Typed contracts

Pydantic v2 models in `src/dataset_generator_m1/models.py` are executable sources of truth. All models forbid unknown fields and are immutable. YAML loading rejects duplicate keys. Generated schemas live in `docs/schema/`.

A composer selects complete typed profiles:

```yaml
schema_version: 2
family: builtin:family/landing
run: builtin:run/landing-standard
assets: builtin:assets/landing
output: builtin:output/standard
sampling: builtin:sampling/landing-standard
scene: builtin:scene/standard
background_recipes: builtin:background_recipes/standard
background_mixing: builtin:background_mixing/standard
appearance: {preset: builtin:appearance/realistic-heavy}
execution: builtin:execution/standard
telemetry: builtin:telemetry/standard
reporting: builtin:reporting/standard
```

References may be built-in IDs, workspace IDs, or paths relative to the composer. Built-in bundles
contain `profile.yaml`, `metadata.json`, and `README.md`. Singleton subjects resolve one complete
profile; appearance resolves one preset plus ordered stage profiles and strict inline effects. A composer
may also provide modeled partial inline values for run, assets, output, sampling, scene, background recipes,
background mixing, execution, telemetry, and reporting. These values are schema-checked before they are applied;
generic untyped YAML deep merging is not part of the composer interface.

Dimensions are always `[width, height]`. Scene/camera values are normalized fractions unless a field
explicitly names pixels or degrees. Appearance transforms are ordered `{id, type, probability, params}`
records and must exist with the given signature in the installed Albumentations version. Stable IDs
are required by controlled studies and shipped profiles.

Each packaged family definition supplies an ordered class catalog, ordered regex mapping rules, and its rotation policy. Every decoded foreground must match exactly one rule and one declared class. Background and foreground sampling support group and per-asset weights; configured and observed distributions are audit output.

## 3. Resolution and catalog validation

Composer resolution loads every referenced profile, packaged family definition, recipe catalog, profile
metadata, and declared overrides into one immutable contract hash. The run records its reference graph,
source hashes, profile metadata, and overrides. Validation must fail before generation on schema errors,
unsupported transforms, invalid references or recipes, missing roots, decode failures, ambiguous class
mappings, empty classes, or zero effective weights.

Precedence is referenced profiles, composer inline values, an optional override file, declared common CLI
options, and repeated typed `--set` leaves. Later `--set` values win. Override files participate in source
hashes; applied leaves are retained in the resolved contract and run manifest. Unknown paths, mapping-valued
`--set`, and invalid final types fail before output creation. See [CONFIGURATION.md](CONFIGURATION.md).

The asset catalog records collision-safe logical paths, dimensions, mode, SHA-256, a perceptual fingerprint, group, class mapping, and optional background tags, aliases, exclusions, seamlessness, texture kind, and approved recipe roles. Its stable fingerprint participates in resume compatibility. Exact and perceptual duplicate groups are reported as catalog-quality evidence.

## 4. Deterministic scene geometry

The planner owns all choices. Independent streams are derived from `(run_seed, slot, candidate_attempt,
stream_name)` for geometry, foreground selection, recipe selection, negatives, synthesis, and
appearance. Inside appearance, activation and Albumentations parameters use streams derived from the
stage and stable transform ID; background affine and final appearance have separate streams.

For each candidate it:

1. Creates an overscanned scene canvas.
2. Samples an aspect-preserving rectangular camera window with center jitter.
3. Samples one constrained corner-offset homography and rejects non-convex or collapsed quadrilaterals.
4. Samples a background recipe and intentional-negative state.
5. Treats `instances_per_image` as an attempt count and records bounded structured diagnostics for exhausted placement attempts.
6. Samples local asset rotation, size, and placement with configured bbox spacing.

The renderer composes each object-local transform with the same `scene_to_output` matrix used for the background. It warps RGB and alpha through the identical composed transform, rejects invisible or excessively truncated instances, and computes an axis-aligned detection box from final visible coverage at the family alpha threshold. It retains full projected coverage before later-object occlusion and visible coverage after later objects are composited. The default clipped/full transformed-box threshold is `0.70`. Incomplete background coverage is a fatal candidate geometry defect. Non-negative candidates with no accepted objects are rejected and retried.

Square rotation preserves the full rotated canvas. Circle rotation returns the tight visible-alpha object. Appearance can change pixels but cannot change the plan, scene matrix, or annotations.

Nested placement is not implemented. Its accepted future model is family-declared `typed-mixed`:
`attached-local` composes child and parent transforms, while `projected-contained` independently places
a child inside the parent projected silhouette. See
[Decision 001](decisions/001-typed-nested-placement.md). Landing and manometro currently declare no
nested compatibility and remain flat scenes.

## 5. Background recipes

Recipes are a separate versioned YAML catalog. A profile assigns probabilistic recipe weights; weights are normalized and never enforced as quotas. Each recipe is a curated typed DAG with a version, output node, optional tileability capability, and explicit allowed cross-material group pairs. Arbitrary expressions, Python callables, recursive includes, unknown operators, cycles, and forward references are invalid.

The initial operator set is:

- `sample_asset`
- `resize_crop`
- `colorspace_convert`
- `channel_extract`
- `channel_compose`
- `palette_transfer`
- `mask_normalize`
- `linear_blend`
- `multiband_blend`
- `displace`

Processing uses float32 RGB `[0,1]`. Color-space conversions are explicit. Blend masks are scalar fields; displacement uses separate bounded X/Y fields and OpenCV destination-to-source remapping. Displacement with invalid coordinates or a near-folded Jacobian is rejected. Multiple source slots prefer distinct assets and record audited reuse when constraints force it. Same-material selection is default; a cross-material pair must be named in the recipe allow-list.

Hard failures include invalid output type/shape/range, NaN/Inf, near-constant output, severe clipping, displacement foldover, uncovered pixels, and failed seam validation for a recipe claiming tileability. The initial warning metrics are luminance and chroma spread, saturation, low/high-frequency energy, seam score, clipping, reuse, and cross-group use. Preview artifacts are the calibration surface for future threshold changes.

Every result records recipe ID/version, graph hash, source logical paths and hashes, group/role/reuse, sampled node parameters, node timings, QA, and warnings. Synthesis caching is intentionally absent until benchmark evidence justifies it.

## 6. Telemetry and display

Monotonic high-resolution timing is persisted for planning, synthesis, every recipe node, rendering,
mask encoding/writing, image encoding/writing, and coordinator work represented in the pool. Renderer records include exclusive
background effects/affine/perspective/coverage; foreground decode/effects/rotation/resize/warp/
visibility/composition/annotation; and final effects. Per-effect traces retain applied parameters.
Candidate rejection records retain incurred stage cost. Aggregates include count, total, mean, median,
p90, p95, and p99; run summaries also include throughput, candidate/object/background rejection rates,
top causes, rejection cost, class/group/negative distributions, configured/observed recipe mix, QA
distributions, warnings, and resource peaks.

Accepted sample records retain the sampled scale, rotation, requested object count, stable object-attempt
identity, and output region needed to calculate conditional rejection rates. Rejected object attempts
retain asset/class/group identity, estimated size, blocking counts, a bounded spatial-bin histogram,
the best failed placement, projected/clipped boxes, clipped sides, visibility, region, and rejection
stage. These diagnostics do not participate in scene planning and therefore cannot change geometry or
annotations.

The coordinator owns one Rich `Console`, Live display, logging, pool commits, and ordered JSONL output.
Process workers never print. Live/full display shows accepted and attempted progress, throughput/ETA,
worker/in-flight/queue state, stage p50/p95 bottleneck, rejection causes, recipe mix, and the latest plus
peak process-tree resources. Plain output is periodic and line-oriented; quiet preserves artifacts and
fatal status.

Telemetry profiles declare `resource_sampling: continuous|off` and `resource_interval_seconds`.
`continuous` is the default. A coordinator-owned background monitor samples the coordinator, direct
workers, and other descendants independently of sample commits. Sanitized records use monotonic session
elapsed time, aggregate CPU/RSS/process I/O, process counts, and run state; they never include PIDs,
hostnames, usernames, or absolute paths. The monitor uses a bounded buffer. The coordinator drains it to
`metrics.jsonl`; overflow and inaccessible/disappearing-process counts remain visible. Sampling continues
while paused, final samples are flushed for every terminal state, and resume appends a new telemetry
session without rewriting history. `off` is the explicit controlled-comparison opt-out.

The first interrupt stops normal execution, lets the active process-pool shutdown drain completed bounded work, marks the pool interrupted/resumable, and writes a final summary. A second interrupt is allowed to force Python termination. Wall-time and rejection-rate policies are profile fields. Generation consumes the deep preflight contract described in [PREFLIGHT.md](PREFLIGHT.md): validation, conservative free-disk estimation, evidence-backed ETA range, warnings, optional disposable probes, and exact warning receipts. A remaining-space guard still protects an active run.

## 7. Generation pool and resume

Pool layout:

```text
POOL/
  run.json
  samples.jsonl
  rejections.jsonl
  metrics.jsonl
  summary.json
  images/
  masks/             # one safe cropped-alpha archive per sample
  qa/index.html
  state/              # internal atomic commit journal
```

Pool schema v2 is mask-capable by default. `run.json` is immutable and contains the resolved profile/family/recipes, run identity, contract and catalog hashes, capabilities, annotation policy, sanitized invocation, preflight result and receipt binding, dependency/schema/generator versions, Git commit/dirty state, and sanitized hardware summary. Usernames, hostnames, environment dumps, and absolute source paths are excluded.

Images and mask archives are atomically replaced before an fsynced per-record commit journal is updated and the readable JSONL stream is appended. Each annotation has a deterministic instance ID referencing cropped uint8 full/visible alpha coverage, with identical semantics deduplicated inside a non-pickle NPZ archive. Archive, array, shape, origin, and hash evidence is inspectable. Resume reconciles JSONL from that journal after a partial append. Names combine a readable run label, zero-padded slot, and stable hash. Resume is permitted only when contract, catalog, and pool schema match. Pool-v1 remains inspectable and detection-exportable but cannot resume into v2. Completed slots are not regenerated; rejected attempt indices continue deterministically. Summary status is `complete`, `interrupted`, or `failed`.

`control.json` is the atomically replaced desired/actual state record; `control-events.jsonl` is its fsynced audit stream. Pause drains the current bounded work window before the coordinator idles, continue reuses that coordinator, and stop produces an interrupted/resumable pool. Live ETA excludes paused time and begins a fresh measurement window after resume replay. The normative operator workflow is in [RUN_CONTROL.md](RUN_CONTROL.md).

## 8. Preview, benchmark, compare, and export

Scene preview writes one QA pool per variant. A shared seed/slot stream preserves asset choices and normalized random quantiles across variants. Background preview writes samples for every recipe plus source, node timing, QA, warning, and HTML gallery evidence.

Benchmark uses warmups and deterministic plans, separately measuring scene computation, encoding, and writing, and records environment identity. Compare accepts a run, benchmark, preview, or export artifact and writes JSON plus HTML differences.

The augmentation study reuses the production planner, synthesizer, and renderer. It synthesizes one
background per fixture, balances treatment order on one worker, enforces identical geometry/source/
mask/annotation signatures, and records exclusive effect parameters and timings. Its full ignored
bundle contains `study.json`, `measurements.jsonl`, `summary.json`, an image-first HTML report, gallery,
difference views, and a contact sheet. `AtmosphericFog` from the archived `a3dec1f` profile is represented
only by a disclosed `RandomFog` approximation. Timing claims are paired and environment-local; no
cross-machine thresholds are normative.

The placement study reuses normal pool generation and then reads its committed evidence. It writes a
JSON/JSONL summary plus an image-first report, spatial heatmap, and bounded failed-plan overlays. Normal
pools retain compact diagnostics; rejected-plan images exist only in explicit ignored studies. The
study never tunes spacing, attempts, visibility thresholds, or acceptance policy.

Export validates every source pool before creating its destination, merges compatible pools, builds a union class catalog, remaps class IDs, resolves identity and filename collisions, and writes YOLO images, labels, `data.yaml`, and `export.json`. Detection remains the default. `--task segmentation` projects the selected `family|visible|full` exact mask into one measured polygon per instance. The bounded projection targets rasterized IoU `>= 0.995` and absolute area error `<= 1%`; holes and disconnected components produce deterministic best-effort polygons and `complete_with_warnings`, while exact masks remain canonical. Serialized provenance contains logical pool IDs, schema/contract/catalog hashes, and run-manifest hashes, never absolute source-pool paths. Split assignment is deterministic.

The deep split-planning module unions samples sharing foreground or synthesized-background sources,
reports connected component sizes, per-class component support, negatives, requested/achievable sample
distributions, and deterministic deviation metrics. It compares hash, greedy sample-balance, and greedy
class-balance assignments. The production policy remains hash assignment. `--analyze-only` requires
`asset-disjoint`, does not require `--output-dir`, and creates no export tree. Normal asset-disjoint
exports embed the same analysis; structural fragility or material imbalance yields
`complete_with_warnings` without changing assignment policy or enforcing quotas.

## 9. Acceptance and non-goals

The test suite covers strict profiles, duplicate keys, shipped examples, asset mappings, geometry/mask boxes, RNG isolation, recipe operators and provenance, telemetry fake clocks and aggregates, CLI JSON/display behavior, atomic pools/resume, process equivalence, and collision-safe export.

Pool-v2 stores exact annotation evidence and supports measured YOLO instance-segmentation export. Pool-v1 remains detection-only. Production nested placement (#31), COCO/RLE export, a GUI, model training/evaluation, multi-family runs, exact recipe quotas, GPU/distributed execution, continuous process-tree monitoring, public Python API stability, legacy migration, and unmeasured caching remain outside the current contract.
