# Optional BlenderProc research harness

Run this workflow from a **source checkout**. Blender is not a generator dependency or selectable
core backend. The wrapper is pinned to BlenderProc2.8.0 / Blender4.2.1; actual rendering runs in
Blender's Python3.11, separately from the project's Python3.13/3.14 environment.

```sh
uv venv .cache/blenderproc-venv --python 3.13
uv pip install --python .cache/blenderproc-venv/bin/python -r experiments/blenderproc/requirements.txt
uv run python scripts/blenderproc_pilot.py assets --output-dir outputs/blender-assets
uv run python scripts/blenderproc_pilot.py bridge --assets-dir outputs/blender-assets --foreground-dir foregrounds/landing_pad_foregrounds --output-dir configs/local/blender-bridge
```

`assets` fetches only the reviewed five CC0 manifests in `assets/`, verifies hashes and reuses valid
local files offline. AmbientCG archives use the existing bounded acquisition path; HDR files have
bounded HTTPS downloads. Raw files stay ignored. Inspect and adjust the generated normal2D composers
before generation. The bridge uses only color maps as backgrounds, a planar UV recipe, normal core
pool/evaluation workflows, and either pristine or existing surface-camera appearance plus opt-in
premultiplied filtering. It is not another2D renderer.

Create a valid reference pad pool using a generated composer. Copy `pilot.example.json` to a local
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
a fresh study. The parent watches the complete Blender process tree at0.25s, stops at2GiB available
RAM,10GiB summed RSS,16MiB additional global swap-out or the remaining study budget, and records the
stop. Guards are retained rather than lowered. Budget-limited output may still be exported explicitly.

## Physical and camera assumptions

Nominal panels are1m wide (square1×1m; rectangle1×0.75m),3mm thick, opaque, rigid and flat. Both use class
`pad`. UVs preserve artwork aspect. Plastic uses metallic0, transmission0 and IOR1.46 with selectable
roughness and fine bump response. Ground UV scale is metres per tile; normal maps alter appearance,
not support geometry. Geometry, contact and coarse environmental casters are deliberately simple.
The source maps are PBR assets, not measured target materials.

The reference pool supplies target/count/projected-width support and source2D images. World placement
backprojects reference centers through the configured camera. Rotation-aware camera distance aims
for similar target widths; measured achieved distributions remain evidence, not calibrated equality.
Closeups/clipping/overlap/hidden/negative diagnostics are separate cases. Do not infer physical camera
parameters from the normalized2D settings.

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
intentional negatives are explicit. Nothing changes normal2D acceptance. Appearance/noise/shadows do
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
wall time are not automatically benchmarked. The live pilot was exercised on Linux CPU; Windows CI
covers the host contracts/core workflow, not a native Blender render. Report authoring also requires
Pillow and NumPy (core dependencies) plus optional Matplotlib:

```sh
uv run --with matplotlib python scripts/report_blender_comparison.py --study outputs/experiments/pilot --pristine PATH_TO_PRISTINE_POOL --surface PATH_TO_SURFACE_POOL --output outputs/experiments/pilot-compact
```
