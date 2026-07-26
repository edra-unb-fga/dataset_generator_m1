# Dataset Generator M1 Normative Specification

Version 1 is a clean schema break. Legacy `dataset_type` profiles and legacy output manifests are invalid and have no migration layer. `CONTEXT.md` defines canonical terminology.

## 1. Public commands

The stable command surface is:

```text
validate --config PROFILE
preview scenes --config PROFILE [--variants VARIANTS] --samples N --output-dir DIR
preview backgrounds --config PROFILE --samples-per-recipe N --output-dir DIR
generate --config PROFILE [--num-images N] --output-dir DIR [--resume] [--workers auto|N] [--qa-samples N]
benchmark --config PROFILE --output-dir DIR [--samples N] [--warmup N]
compare --left ARTIFACT --right ARTIFACT --output-dir DIR
export --pool DIR [--pool DIR...] --format yolo --strategy random|stratified|asset-disjoint --splits ... --output-dir DIR
```

Every leaf command accepts `--display auto|live|full|plain|quiet` and `--output-format human|json`. `auto` selects Rich Live only for an interactive terminal. JSON disables generation display and emits exactly one versioned result or error document. Rich follows normal terminal and `NO_COLOR` behavior.

Only `num_images` and `qa_samples` are deep-profile operational overrides. Experiments use named variant YAML overlays, which are validated after merge.

## 2. Typed contracts

Pydantic v2 models in `src/dataset_generator_m1/models.py` are executable sources of truth. All models forbid unknown fields and are immutable. YAML loading rejects duplicate keys. Generated schemas live in `docs/schema/`.

A generation profile has these root fields:

```yaml
schema_version: 1
family: landing
run: {}
assets: {backgrounds: {}, foregrounds: {}}
output: {image_size: [width, height]}
sampling: {}
scene: {}
background_synthesis: {}
appearance: {background: [], foreground: [], final: []}
telemetry: {}
report: {}
```

Dimensions are always `[width, height]`. Scene/camera values are normalized fractions unless a field explicitly names pixels or degrees. Appearance transforms are ordered `{type, probability, params}` records and must exist with the given signature in the installed Albumentations version.

Each packaged family definition supplies an ordered class catalog, ordered regex mapping rules, and its rotation policy. Every decoded foreground must match exactly one rule and one declared class. Background and foreground sampling support group and per-asset weights; configured and observed distributions are audit output.

## 3. Resolution and catalog validation

Profile resolution loads the profile, packaged family definition, recipe catalog, optional background metadata, and declared operational overrides into one immutable contract hash. Validation must fail before generation on schema errors, unsupported transforms, invalid recipe references, missing roots, decode failures, ambiguous class mappings, empty classes, or zero effective weights.

The asset catalog records collision-safe logical paths, dimensions, mode, SHA-256, a perceptual fingerprint, group, class mapping, and optional background tags, aliases, exclusions, seamlessness, texture kind, and approved recipe roles. Its stable fingerprint participates in resume compatibility. Exact and perceptual duplicate groups are reported as catalog-quality evidence.

## 4. Deterministic scene geometry

The planner owns all choices. Independent streams are derived from `(run_seed, slot, candidate_attempt, stream_name)` for geometry, foreground selection, recipe selection, negatives, synthesis, and appearance.

For each candidate it:

1. Creates an overscanned scene canvas.
2. Samples an aspect-preserving rectangular camera window with center jitter.
3. Samples one constrained corner-offset homography and rejects non-convex or collapsed quadrilaterals.
4. Samples a background recipe and intentional-negative state.
5. Treats `instances_per_image` as an attempt count and records exhausted placement attempts.
6. Samples local asset rotation, size, and placement with configured bbox spacing.

The renderer composes each object-local transform with the same `scene_to_output` matrix used for the background. It warps RGB and alpha through the identical composed transform, rejects invisible or excessively truncated instances, and computes an axis-aligned detection box from the final alpha mask. The default clipped/full transformed-box threshold is `0.70`. Incomplete background coverage is a fatal candidate geometry defect. Non-negative candidates with no accepted objects are rejected and retried.

Square rotation preserves the full rotated canvas. Circle rotation returns the tight visible-alpha object. Appearance can change pixels but cannot change the plan, scene matrix, or annotations.

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

Monotonic high-resolution timing is persisted for planning, synthesis, every recipe node, rendering, encoding/writing, and coordinator work represented in the pool. Candidate rejection records retain incurred stage cost. Aggregates include count, total, mean, median, p90, p95, and p99; run summaries also include throughput, candidate/object/background rejection rates, top causes, rejection cost, class/group/negative distributions, configured/observed recipe mix, QA distributions, warnings, and resource peaks.

The coordinator owns one Rich `Console`, Live display, logging, pool commits, and ordered JSONL output. Process workers never print. Live/full display shows accepted and attempted progress, throughput/ETA, worker/in-flight/queue state, stage p50/p95 bottleneck, rejection causes, recipe mix, and memory. Plain output is periodic and line-oriented; quiet preserves artifacts and fatal status. Resource snapshots use low-rate psutil sampling across coordinator and child processes for CPU, RSS, and process I/O.

The first interrupt stops normal execution, lets the active process-pool shutdown drain completed bounded work, marks the pool interrupted/resumable, and writes a final summary. A second interrupt is allowed to force Python termination. Wall-time and rejection-rate policies are profile fields. Generation performs a conservative free-disk preflight and a remaining-space guard.

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
  qa/index.html
  state/              # internal atomic commit journal
```

`run.json` is immutable and contains the resolved profile/family/recipes, run identity, contract and catalog hashes, sanitized invocation, dependency/schema/generator versions, Git commit/dirty state, and sanitized hardware summary. Usernames, hostnames, environment dumps, and absolute source paths are excluded.

Images are atomically replaced before an fsynced per-record commit journal is updated and the readable JSONL stream is appended. Resume reconciles JSONL from that journal after a partial append. Names combine a readable run label, zero-padded slot, and stable hash. Resume is permitted only when contract and catalog fingerprints match. Completed slots are not regenerated; rejected attempt indices continue deterministically. Summary status is `complete`, `interrupted`, or `failed`.

## 8. Preview, benchmark, compare, and export

Scene preview writes one QA pool per variant. A shared seed/slot stream preserves asset choices and normalized random quantiles across variants. Background preview writes samples for every recipe plus source, node timing, QA, warning, and HTML gallery evidence.

Benchmark uses warmups and deterministic plans, separately measuring scene computation, encoding, and writing, and records environment identity. Compare accepts a run, benchmark, preview, or export artifact and writes JSON plus HTML differences.

Export merges compatible pools, builds a union class catalog, remaps class IDs, resolves identity and filename collisions, and writes YOLO detection images, labels, `data.yaml`, and `export.json`. Split assignment is deterministic. `asset-disjoint` unions samples sharing foreground or synthesized-background sources before assigning a component to one split.

## 9. Acceptance and non-goals

The test suite covers strict profiles, duplicate keys, shipped examples, asset mappings, geometry/mask boxes, RNG isolation, recipe operators and provenance, telemetry fake clocks and aggregates, CLI JSON/display behavior, atomic pools/resume, process equivalence, and collision-safe export.

Initial output is YOLO object detection. Stored instance masks are internal geometry evidence; segmentation export remains a later roadmap item. Also out of scope are a GUI, model training/evaluation, multi-family runs, exact recipe quotas, GPU/distributed execution, deep hardware monitoring, public Python API stability, legacy migration, and unmeasured caching.
