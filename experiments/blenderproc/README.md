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

`assets` fetches only the reviewed five CC0 manifests in `assets/`, verifies hashes and reuses valid
local files offline. AmbientCG archives use the existing bounded acquisition path; HDR files have
bounded HTTPS downloads. Raw files stay ignored. Inspect and adjust the generated normal 2D composers
before generation. The bridge uses only color maps as backgrounds, a planar UV recipe, normal core
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
a fresh study. The parent watches the complete Blender process tree at 0.25 s, stops at 2 GiB available
RAM, 10 GiB summed RSS, 16 MiB additional global swap-out or the remaining study budget, and records the
stop. Guards are retained rather than lowered. Budget-limited output may still be exported explicitly.

## Physical and camera assumptions

Nominal panels are1m wide (square1×1m; rectangle1×0.75m),3mm thick, opaque, rigid and flat. Both use class
`pad`. UVs preserve artwork aspect. Plastic uses metallic0, transmission0 and IOR1.46 with selectable
roughness and fine bump response. Ground UV scale is metres per tile; normal maps alter appearance,
not support geometry. Geometry, contact and coarse environmental casters are deliberately simple.
The source maps are PBR assets, not measured target materials.

The reference pool supplies target/count/projected-width support and source 2D images. World placement
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

## Annotation and output contract

RGB can have DOF/motion blur; masks use sharp geometry at reference pose/frame0. Visible masks include
true mesh occlusion. Full masks isolate each target. Lens distortion uses the same map with nearest
sampling for masks and interpolated RGB. Boxes come from final visible masks, not projected vertices.
Masks are canonical binary full/visible arrays with COCO RLE. No optical coverage claim is made.

Candidates with any0<visible/full in-frame support<25% are resampled up to8 attempts; cost and reasons
are retained. Fully hidden targets have no annotation; accidental empty positives are rejected and
intentional negatives are explicit. Nothing changes normal 2D acceptance. Appearance/noise/shadows do
not alter reference masks.

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
them null/omitted for automatic defaults. Older local configs containing `threads:6` still explicitly
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
workers. All worker trees share the original host-RAM/swap/time guards; Blender configuration,
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
metadata, approved artwork, hash-pinned PBR/HDR files and a validated reference pool with referenced
QA artifacts. It omits Git state, caches, arbitrary workspace files and credentials. The input bundle
identity enters the new study contract. Absolute local input roots are relocated; source contents
and source-asset hashes remain pinned. Inspect the manifest before sharing a bundle outside your
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
