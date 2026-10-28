# Optional BlenderProc research harness

Run this workflow from a **source checkout**. Blender is not a generator dependency or selectable
core backend. The wrapper is pinned to BlenderProc 2.8.0 / Blender 4.2.1; actual rendering runs in
Blender's Python 3.11, separately from the project's Python 3.13/3.14 environment.

```sh
uv venv .cache/blenderproc-venv --python 3.13
uv pip install --python .cache/blenderproc-venv/bin/python -r experiments/blenderproc/requirements.txt
uv run python scripts/blenderproc_pilot.py assets --output-dir outputs/blender-assets
uv run python scripts/blenderproc_pilot.py bridge --assets-dir outputs/blender-assets --foreground-dir foregrounds/landing_pad_foregrounds --output-dir configs/local/blender-bridge
```

`assets` fetches the reviewed CC0 manifests in `assets/`, verifies hashes and reuses valid
local files offline. A selection can contain 1–6 ground materials and 1–3 HDR environments; these are current
validated harness limits, not a two-asset limit. AmbientCG archives use the existing bounded acquisition path; HDR files have
bounded HTTPS downloads. Raw files stay ignored. Inspect and adjust the generated normal 2D composers
before generation. The bridge discovers verified material manifests, uses only their color maps as backgrounds in legacy
material order followed by additional materials, and uses a planar UV recipe, normal core
pool/evaluation workflows, and either pristine or existing surface-camera appearance plus opt-in
premultiplied filtering. It is not another 2D renderer.

Create a valid reference pad pool using a generated composer. Copy `pilot.example.json` (1280²), `pilot-fast.example.json` (640²), or the explicit raw-GPU
`pilot-reference.example.json` (128/512 samples) to a local
configuration, update paths, and prepare a fresh output. Relative paths resolve against the config.

```sh
uv run python scripts/blenderproc_pilot.py prepare --config configs/local/pilot.json --output-dir outputs/experiments/pilot
uv run python scripts/blenderproc_pilot.py render --output-dir outputs/experiments/pilot --blenderproc .cache/blenderproc-venv/bin/blenderproc --blender-install-path .cache/blender
uv run python scripts/blenderproc_pilot.py export --output-dir outputs/experiments/pilot --yolo
uv run python scripts/blenderproc_pilot.py report --output-dir outputs/experiments/pilot
uv run python -m dataset_generator_m1 evaluate prepare --manifest outputs/experiments/pilot/evaluation-visible.json --output-dir outputs/experiments/pilot/prepared-visible
```

`render --jobs ID...` selects prepared jobs for diagnostics. Completed outputs are atomically committed
and hash-checked on restart. Exclusive coordinator ownership prevents concurrent render writers; exporting freezes the completed dataset against later appended scenes. Config, reference pool, asset/artwork revisions, source and job plan are
bound into study identity. Rendering time accumulates across retries/resume; a changed contract needs
a fresh study. The parent watches the complete Blender process tree at 0.25 s and enforces the saved
execution catalog's host RAM, process-tree RSS, system swap-out and time guards. The historical catalog
uses a 2 GiB available-RAM floor and 10 GiB summed-RSS cap; these are fixed research safeguards, not
machine-independent capacity estimates. An optional `min_gpu_free_mib` guard stops GPU work if sampled
free VRAM falls below its limit or NVIDIA telemetry is unavailable. GPU and host RAM are separate.
Budget-limited output may still be exported explicitly.

For one-command setup, generate a fresh policy and prepare the study together:

```sh
uv run python scripts/prepare_blenderproc_run.py \
  --config configs/local/pilot.json \
  --output-dir outputs/experiments/l4-camera-run \
  --screen-profile colab-l4-camera-study --gpu-guard required
uv run python scripts/blenderproc_pilot.py render \
  --output-dir outputs/experiments/l4-camera-run/study \
  --blenderproc .cache/blenderproc-venv/bin/blenderproc --blender-install-path .cache/blender
```

The optional L4 camera selection is an explicit experimental recommendation, not a universal hardware
default: it selects 6 workers × 2 threads for up to 640² and 4 × 1 for larger images. The 1280² 4 × 1
screen was a single short comparison. Omit `--screen-profile` to preserve the config's selection.
The setup prints the resolved guards and retains the measured basis, policy and resolved config beside
`study/`. Render and resume use that frozen policy; a fresh setup remeasures current headroom. A failed
setup keeps its status and diagnostics in the output directory; retry in a new directory.

`--gpu-guard auto` (the default) measures NVIDIA VRAM when an NVIDIA tool is present and a GPU or
automatic profile may use it; an explicitly selected GPU profile fails if NVIDIA telemetry is missing.
`required` insists on NVIDIA VRAM telemetry, and `off` explicitly opts out of measuring it. The
adaptive GPU utility currently supports exactly one NVIDIA GPU; on multi-GPU hosts it fails rather
than selecting a card implicitly. The lower-level monitor currently guards against the lowest free
VRAM among NVIDIA devices, which is conservative but does not isolate the selected GPU. On systems
without NVIDIA telemetry, automatic selection may still choose a non-NVIDIA GPU, so setup reports
that no VRAM guard was measured. Use a separately reviewed policy when that limitation matters.

To create a fresh, machine-specific catalog, adjust the fractions and reserve floors in
`execution/adaptive-guards.json`, then run on the machine that will render:

```sh
uv run python scripts/blenderproc_adaptive_guards.py \
  --policy experiments/blenderproc/execution/profiles.json \
  --settings experiments/blenderproc/execution/adaptive-guards.json \
  --output configs/local/adaptive-execution.json --gpu
```

Omit `--gpu` for CPU-only work. The command refuses to overwrite an existing policy and saves a
`.basis.json` with measured headroom and parameters. Set `execution_policy` in the pilot config to the
new file before preparing; the prepared study freezes the resolved guards. Measure again for a new
study on different hardware or if headroom has materially changed. Summed RSS counts shared pages more
than once, so this is a conservative monitoring threshold rather than a physical-memory forecast.
The adaptive fractions are configurable provisional safeguards, not proven universal defaults. A guard
stop is evidence to investigate, not a reason to silently weaken the limits.

## Physical and camera assumptions

Nominal panels are1m wide (square1×1m; rectangle1×0.75m),3mm thick, opaque, rigid and flat. Both use class
`pad`. UVs preserve artwork aspect. Plastic uses metallic0, transmission0 and IOR1.46 with selectable
roughness and fine bump response. Ground UV scale is metres per tile; normal maps alter appearance,
not support geometry. Geometry, contact and coarse environmental casters are deliberately simple.
The source maps are PBR assets, not measured target materials.

The reference pool supplies target/count/projected-width support and source 2D images. The shared
comparison core targets 20 independent reference intents, preserving artwork and source hashes, count,
size coverage intent and annotation conventions. Exact paired controls apply within an engine; the
2D and 3D outputs do not promise pixel matching or identical projections. `scene_offset` selects the
starting reference row and each job records `reference_scene_index`; selection wraps modulo the pool
length. Check the recorded indices against the actual pool before making a holdout claim. The planned
20-intent core includes all reference layouts; the reserved phase uses indices 4–9 with a new seed,
while development review uses 0–2. Treat reserved results as new synthetic combinations, not held-out
layouts or real holdout evidence, and do not tune after reserved review. World placement
backprojects reference centers through the configured camera. Rotation-aware camera distance aims
for similar target widths; measured achieved distributions remain evidence, not calibrated equality.
Closeups/clipping/overlap/hidden/negative diagnostics are separate cases. Do not infer physical camera
parameters from the normalized 2D settings.

Expose focal length/sensor width/principal point, view/azimuth/roll/distance scale, aperture/focus,
continuous camera translation/shutter time, Brown–Conrady distortion, exposure/tone response and a
bounded post-display RGB Gaussian noise approximation. A scalar noise control does not implement
Poisson/read noise, gain, Bayer sampling or demosaicing. No camera-specific calibration is claimed.

Explicit sun uses diffuse overcast HDR fill to avoid adding a second misaligned HDR sun. The
`environment` treatment uses the partly cloudy HDR alone. `shade` is dim diffuse-sky illumination,
not a reconstructed deployment location. Night supports one/mixed artificial area lights and weak
ambient fill. Haze uses a bounded volume, hidden during geometric annotation passes.

## Saved surface controls

Treatments are strict saved JSON data; see `pilot.schema.json` and
`studies/surface-integration.json` for the complete fields, bounds and examples. `roughness` is the
nominal plastic roughness. `pad_bump_strength` and `ground_normal_strength` separately control pad
bump and ground normal response; when omitted or null each falls back to legacy `normal_strength`.
`pad_bump_distance_m` controls bump amplitude, not mesh displacement. `uv_scale_m`,
`uv_rotation_degrees` and `ground_uv_offset` share one ground mapping across color, roughness and
normal textures. HDR selection uses zero-based `environment_index`, rotation and strength; omitted
selection preserves the legacy lighting-dependent first/second environment choice, falling back to
the first when only one is available.

A `lamps` list supplies area-light location, color, target, power and size. Omitting it preserves the
legacy lighting-specific area lamps; an explicit empty list selects no area lamps. A sun treatment
still adds its sun light. `casters` enables deterministic,
grounded procedural shadow casters using saved count, seed, distance, height and width; count zero
selects none. With `shadows` enabled and `casters` omitted or null, the legacy three-post fixture is
retained. New procedural casters are camera-invisible; scene results record their resolved transforms
and light/material diagnostics. These coarse fixtures are not a reconstructed environment.

Optional `wear` uses the same bounded `SurfaceWear` parameters and deterministic fields as 2D RGB
wear. `wear_seed` can explicitly fix the field seed; otherwise preparation derives a seed per job and
object. Host preparation generates source-sized, registered 8-bit PNGs in artwork UV coordinates
with top-left origin: sRGB RGB/RGBA albedo and linear grayscale roughness and height. Original alpha
is preserved; height changes shading only. The renderer treats roughness and height as non-color data.
The manifest records configuration, seed, map dimensions, encoding, paths and hashes, and maps are
verified before render/resume. These are qualitative plastic approximations, not measured reflectance.

`quality_treatments` omitted or null schedules quality jobs for the first treatment, preserving the
historical default. `[]` schedules none; a nonempty list schedules quality jobs only for those IDs.
The phase controller supplies this selection explicitly. Production 2D defaults remain unchanged.

## Round-three surface study

The file-backed matrix declares recipes, phase selections, resolutions, sample counts and budgets:
`experiments/blenderproc/studies/surface-integration.json`. `core` and `wear` are shared-core
comparisons; candidates isolate mapping/context, `stress-wear` is deliberately heavy, and `glint`
and `night` are specialists with declared deviations. Their goals are experimental, not calibrated
training recommendations. `studies/surface-2d.json` specifies the complementary 2D study. Separate
prototype worktrees may explore procedural or CC0 mesh context; mesh import is not promoted into the
main harness or core backend. See `docs/REALISM_ROUND_THREE.md` and
`docs/experiments/surface-integration-v1/README.md` for the agreement and eventual evidence.

Run a fresh phase cell and inspect its shared budget, using saved configuration and matrix paths:

```sh
uv run python scripts/study_surface_integration.py budget --matrix experiments/blenderproc/studies/surface-integration.json --output-dir outputs/experiments/surface-integration
uv run python scripts/study_surface_integration.py run --config configs/local/pilot.json --matrix experiments/blenderproc/studies/surface-integration.json --output-dir outputs/experiments/surface-integration --phase development --cell-id development-01 --blenderproc .cache/blenderproc-venv/bin/blenderproc --blender-install-path .cache/blender
```

Optional `--recipes ID...` selects a nonempty subset of the matrix recipes. Each cell is prepared
fresh, with a unique ID, and `design.json` freezes the matrix contents and SHA-256; each cell's
`surface-origin.json` records phase, recipes and controller SHA-256. Editing the matrix requires a new
study root. `budget.json` conservatively charges interrupted reservations until reconciled against
recorded run evidence. The saved policy caps the shared rendering/probe/warmup/retry budget at 7200 s,
prototype work at 1440 s and each prototype cell at 720 s, while retaining at least 1800 s for final
work. Setup and short local controls are reported separately; the existing RAM/swap safeguards remain.

The matrix targets 640-square previews, 1280-square quality and selected performance confirmation of
2 warmups plus 20 measured outputs across 3 alternating repetitions when budget permits. Incomplete
cells remain exploratory. Report accepted outputs divided by the appropriate common wall time and
keep startup, annotation/retry, encoding/export and resources separate; do not sum concurrent
per-image durations or infer a cross-engine multiplier from different hosts or workloads.

## Annotation and output contract

RGB can have DOF/motion blur; masks use sharp geometry at reference pose/frame0. Visible masks include
true mesh occlusion. Full masks isolate each target. Lens distortion uses the same map with nearest
sampling for masks and interpolated RGB. Boxes come from final visible masks, not projected vertices.
Masks are canonical binary full/visible arrays with COCO RLE. No optical coverage claim is made.

Candidates with any0<visible/full in-frame support<25% are resampled up to8 attempts; cost and reasons
are retained. Fully hidden targets have no annotation; accidental empty positives are rejected and
intentional negatives are explicit. Nothing changes normal 2D acceptance. Appearance, noise and
shading do not alter reference masks; camera-visible caster or occluder geometry can alter visible masks.

Required exports are `coco-visible.json`, `coco-full.json`, evaluation manifests and per-image metadata.
Optional YOLO detection/segmentation conversion is atomic per format, bounded by5min and2000 contour
points per mask; exact COCO remains authoritative. Disconnected/holed masks can be lossy and carry
serialized-polygon fidelity. Failure leaves that entire format unavailable, never partially labeled.
The YOLO artifact is one development set: train/val alias it, explicitly documented; those aliases
must not be used as independent validation. Training/split design is outside this pilot.

`summary.json`, offline HTML, paired images, mask overlays and standalone cost figures are local
review artifacts. Matplotlib is an optional report-authoring dependency. Cold command/setup,
annotation passes, cold/warm same-scene RGB, attempts and encoding are separate. Additional warm
microbenchmark renders consume budget but are excluded from the single-output cost field.

These views test plausible engineering configurations. Real-world model benefit, calibrated materials,
reference camera distributions and unseen deployment performance remain unknown. See
`docs/REALISM_ROUND_TWO.md` and `docs/BLENDERPROC_COMPARISON.md`.

The first render may download/install the pinned Blender runtime beneath `--blender-install-path`;
allow its disk/network setup separately from steady-state generation. Installation and asset-acquisition
wall time are not automatically benchmarked. The live pilot was exercised on Linux CPU and a Colab T4; Windows CI
covers the host contracts/core workflow, not a native Blender render. Report authoring also requires
Pillow and NumPy (core dependencies) plus optional Matplotlib:

```sh
uv run --with matplotlib python scripts/report_blender_comparison.py --study outputs/experiments/pilot --pristine PATH_TO_PRISTINE_POOL --surface PATH_TO_SURFACE_POOL --output outputs/experiments/pilot-compact
```


## Saved hardware execution policies

`execution/profiles.json` contains every device/denoiser/worker/thread/bounce policy and the resource
limits. The scripts interpret this validated data; machine names and tuning values are not embedded
in their control flow. `execution/schema.json` is generated from the host contract.

`execution_profile: "auto"` (the default) probes the actual pinned Blender runtime before launching
workers. Ordered rules select the tested Colab T4 cases, a conservative GPU-OIDN capability fallback,
or the CPU fallback. The small T4 rule requires two available CPUs, at least 12 GiB reported VRAM and
at most 409600 output pixels. These are bounded operational choices from this host, not universal
hardware speed optima. Other hardware uses one worker until it has evidence of its own.

```sh
uv run python scripts/blenderproc_pilot.py profiles
uv run python scripts/blenderproc_pilot.py profiles --policy configs/local/my-blender-policy.json
```

To save a local policy, copy that JSON, edit its rules/settings, then set `execution_policy` in the
study config to its relative filename. Set `execution_profile` to a profile ID for an explicit choice.
Optional study `threads` and `workers` values override the selected profile and are recorded; leave
them null/omitted for automatic defaults. The current worker limit is eight; it is a safety bound,
not evidence that eight workers are optimal on every machine. Older local configs containing `threads:6` still explicitly
request six threads and should remove that value to adopt the saved hardware policy.

CPU-fast and raw-reference profiles are explicit quality choices and never selected as silent
fallbacks. Native GPU OIDN checks advertised support and refuses a capability loss. Unsupported GPU
capabilities select the CPU fallback during automatic resolution; the reason is recorded. An explicit
incompatible GPU profile fails. Resolution, sample count, materials, camera and treatment selection
stay in the study config and do not silently change with hardware.

`execution.json` seals the selected profile/settings, hardware/capabilities, driver/runtime versions,
policy digest and overrides to the prepared study. Every accepted scene records that execution
identity and actual renderer settings. The reproducibility key is the prepared study identity plus
its resolved execution identity. A changed hardware/configuration selection requires a fresh study;
resume verifies completed checksums and selection provenance. Completed selections return without
relaunching Blender. Source changes also require fresh preparation. Historical CPU studies remain
readable/exportable; they cannot append renders under the new source/profile contract.

One coordinator owns the study and partitions disjoint prepared job IDs between persistent Blender
workers. All worker trees share the selected catalog's host-RAM/swap/time guards and optional GPU
free-memory guard; Blender configuration,
Matplotlib cache and temporary directories are isolated. Probe/setup and common concurrent render
wall times are separate entries in `runs.json`. Per-image times must never be summed into aggregate
parallel throughput. Worker completion without all selected scene records is a failure.

## Portable bundle / Colab without a clone

Create a bundle from a valid local study config and downloaded assets:

```sh
uv run python scripts/blenderproc_pilot.py bundle --config configs/local/pilot.json --output-file outputs/pilot-inputs.tar.gz
```

The result reports archive/bootstrap paths and SHA256 values. Upload only those two files with your
configured Colab CLI/MCP, then invoke the generated standalone bootstrap in the runtime:

```sh
python pilot-inputs.tar.gz.run.py pilot-inputs.tar.gz --workspace /content/pilot-workspace --expected-sha256 ARCHIVE_SHA256
```

The same invocation works locally. `uv` must be available; Colab's tested runtime includes it.
The bootstrap verifies every archive member before publishing a workspace, creates the locked host
environment and pinned BlenderProc wrapper, prepares a relocated study, automatically chooses its
hardware profile, renders and exports canonical COCO/evaluator artifacts. BlenderProc installs and
runs headless Blender in its own embedded Python. `MPLBACKEND=Agg` prevents the notebook backend
from leaking into that separate environment. `uv venv` avoids the missing-ensurepip issue observed
with Colab's standard venv command. No Google credentials or remote-session management are bundled.

`--jobs ID...` restricts the prepared jobs. `--blender-install-path DIRECTORY` reuses an existing
managed Blender download across fresh bundles. Use a new workspace per bundle; ordinary interrupted
studies resume through `render` in their extracted source checkout. An interrupted/budget-limited
bootstrap preserves its evidence and requires an explicit later export of partial results.

The explicit file manifest contains only the required source checkout subset, locked dependency
metadata, approved artwork, hash-pinned PBR/HDR files, generated wear derivatives and a validated reference pool with referenced
QA artifacts. It omits Git state, caches, arbitrary workspace files and credentials. The input bundle
identity enters the new study contract. Absolute local input roots are relocated; source contents
and source-asset hashes remain pinned; regenerated wear map hashes are checked against the bundled
derivatives. Create a fresh bundle after any pinned source, config or input change. Inspect the manifest before sharing a bundle outside your
own runtime. Colab allocations remain variable; rerun capability detection in every fresh study.

## Reproducing execution studies

The matrix fixes repetitions, warmups, measured scenes, output dimensions, profile choices and
initialization policy. The driver alternates variant order, preserves scene/seed/source inputs and
checks exact full/visible masks plus measured RGB differences. It saves the driver/matrix digests.

```sh
uv run python scripts/study_blender_execution.py --config configs/local/pilot.json --matrix experiments/blenderproc/benchmarks/renderer-initialization.json --output-dir outputs/experiments/renderer-initialization --blenderproc .cache/blenderproc-venv/bin/blenderproc --blender-install-path .cache/blender
```

`guarded-workers.json` compares concurrency after the initialization change, using accepted images
per common command wall time including startup/warmups. The initialization matrix uses one worker
and complete measured-output time excluding warmup/startup. These metrics are deliberately separate.
The stock/guarded initialization field is an explicit, hashed setting; generic CPU behavior remains
stock unless selected otherwise. See `docs/experiments/blender-execution-v1/` for measured scope,
RGB repeat variability and the final promotion verdict. Broader calibration/real-model quality and
new material/effect studies still belong to the next planning round.


The tested T4 auto profiles enable **guarded renderer initialization**. It applies the same pinned
BlenderProc renderer settings while avoiding assignments that are already active, preserving the
Cycles session between label passes. The explicit `gpu-guarded` profile enables the same experiment
on other hardware; generic GPU and CPU auto profiles retain stock behavior. `cpu-guarded` is a
nonautomatic diagnostic control. Every result records whether the guarded initializer is active.
GPU shading/denoising is not promised byte-identical even in unchanged repeats; full/visible masks,
acceptance and scene settings remain the strict checks. Retained evidence reports both ordinary RGB
repeat variation and paired differences.

The portable bootstrap records setup and execution stage wall times in `bootstrap.json`, including
failed stages, separately from per-image rendering cost.

To regenerate the reviewed execution figures from the retained evidence archive, run
`scripts/report_blender_execution.py --evidence-dir PATH --output-dir PATH` in the host environment
with Matplotlib installed. Optional `--denoising` and `--cpu-study` inputs include the earlier denoising
analysis and local CPU qualification. The authoring script produces Markdown, compact JSON and PNGs.

### Drone camera study

`pilot-drone.example.json` opts new studies into a scene-seeded drone pose. Yaw and
heading-relative tilt direction are uniform; tilt follows the saved bounded exponential.
Treatments and quality variants share the sealed scene pose. The renderer aims at the
reference group, matches its median target width within the saved distance bounds, and
records achieved width and bound failures. A single ordinary pad is centered. Ground
extent follows the projected footprint within saved bounds; a horizon or extent clamp is
recorded. View-relative material mode samples the number of material spans across the
central view, subject to saved tile bounds; fixed-physical mode uses each treatment's
`uv_scale_m`. Result diagnostics retain nominal and achieved values. Existing configs
without `camera_study` retain their scalar camera and 40 m ground behavior.


### Explicit environment geometry

`pilot-environment-mix.example.json` opts into an 80/10/10 weighted open, indoor,
and outdoor mix. The weights need not sum to one; selection is deterministic per scene
and shared by paired treatments and quality levels. The indoor example forces an enclosed
room, with a ceiling above the camera and an area light; the outdoor example forces a
bounded, open-top layout. Walls and ceilings are real renderable meshes and therefore
cast shadows and can occlude the target. Room dimensions adapt to include the camera
and target, so camera height affects their size. Geometry dimensions are recorded in
result diagnostics. HDR world lighting and sun are disabled inside the room; saved
treatment lamps still apply. Omit `environment_mix` for the original open scene.

Environment geometry settings are saved under `environment_geometry_settings`: minimum room
half-width and height, margins around the camera, outdoor wall height, wall thickness, color
and roughness, and indoor area-light power, color, size and ceiling offset. The room expands
to contain the camera and the complete rotated footprints of placed targets. The saved horizontal
camera margin also supplies target-to-wall clearance; result diagnostics record the target extent. `wall_ground_index` chooses the color map of an existing licensed
`grounds` entry; `wall_texture_repeats` sets UV repetitions per face. Set the index to null
for a plain-colored wall. The examples choose the Concrete034 ground entry explicitly; this
is a prototype requiring visual and annotation review, not a calibrated material library.

## Material provenance and completed-cell handoff

Locally supplied non-CC0 ground and environment manifests must declare `license`, `author`,
`source_url`, `license_url`, `attribution`, `restrictions`, `allow_local_render_and_dataset: true`,
and an explicit boolean `allow_redistribution`. These are user-supplied declarations rather than
independent legal verification. Portable input bundles refuse assets without redistribution permission;
existing CC0 shorthand remains valid. The built-in asset downloader and 2D bridge remain CC0-only.

For a completed, settled surface-study cell, package and verify the snapshot between timed commands:

```sh
python scripts/handoff_study_cell.py package --root STUDY --cell CELL --archive CELL.tar.gz
python scripts/handoff_study_cell.py import --archive CELL.tar.gz --output IMPORTS
```

A configured CLI can download a packaged cell with `handoff_study_cell.py colab --remote PATH
--output IMPORTS --cache DOWNLOADS --executable EXECUTABLE --session SESSION`. The controller must
pause the remote study before transfer and wait for transfer and verification before starting a new
timed command. The local lease cannot control a remote machine. A failed archive download restarts
that archive; already verified cells are retained. This interface was tested locally and with a fake
CLI, not against a live Colab runtime in this round.
