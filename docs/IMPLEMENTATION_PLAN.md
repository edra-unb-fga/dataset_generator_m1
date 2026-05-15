# Implementation Plan

## Goal

Build the new synthetic dataset generator described by `NEW ARCHITECTURE.md`. The app generates YOLO image/label pairs for:

- `manometro`: foregrounds from `foregrounds/manometro_foregrounds`, square rotation.
- `landing`: foregrounds from `foregrounds/landing_foregrounds`, circle/tight rotation.

The asset folders are expected at the repository root before generation runs.

Current status: the first implementation pass is in place under `src/dataset_generator_m1/`. It uses the root `backgrounds/` and `foregrounds/` layout, the documented minimal YAML configs, local image-only filter implementations, YOLO output, debug overlays, `data.yaml`, and `manifest.json`.

## Target Repository Layout

```text
backgrounds/
foregrounds/
  landing_foregrounds/
  manometro_foregrounds/
configs/
  landing.yaml
  manometro.yaml
docs/
  CONFIG_SCHEMA.md
  IMPLEMENTATION_PLAN.md
  REFERENCE_NOTES.md
examples/
  configs/
    landing_minimal.yaml
    manometro_minimal.yaml
src/
  dataset_generator_m1/
    __init__.py
    __main__.py
    cli.py
    config.py
    assets.py
    filters.py
    generator.py
    imaging.py
    types.py
tests/
  fixtures/
  test_config.py
  test_geometry.py
  test_annotations.py
  test_pipeline_smoke.py
```

## Pipeline Contract

1. Load config and merge CLI overrides.
2. Discover assets for the selected `dataset_type`.
3. For each output image:
   - Sample per-image random state, crop size, instance count, and shared perspective parameters.
   - Generate a tiled background large enough for affine/perspective work and the final centered crop.
   - Generate one or more foreground instances with dataset-specific rotation behavior.
   - Apply the same perspective parameters to background and foreground surfaces.
   - Place foreground instances inside the already selected final crop bounds.
   - Assemble RGBA foregrounds over RGB/RGBA background.
   - Center crop to `output.image_size`.
   - Generate YOLO annotations using transformed visible bboxes in final crop coordinates.
   - Apply final image-only filters.
   - Write image, `.txt` label, `data.yaml`, manifest row, and optional debug overlays.

## Milestones

### 1. Project Skeleton

- Status: implemented.
- Package added under `src/dataset_generator_m1`.
- Dependency metadata added in `pyproject.toml` with `opencv-python`, `numpy`, `pillow`, and `pyyaml`.
- Console module entry point added through `python -m dataset_generator_m1`.

Acceptance:

- `python -m dataset_generator_m1 --help` works.
- Tests can import package modules.

### 2. Config System

- Status: implemented for `examples/configs/*.yaml`.
- Defines a config loader matching `docs/CONFIG_SCHEMA.md`.
- Merges CLI overrides for `dataset_type`, `config`, `num_images`, `output_dir`, `debug`, `debug_dir`, and `backgrounds_dir`.
- Validates top-level keys, known nested keys, ranges, output format, foreground rotation mode, supported filters, and supported filter parameter names.

Acceptance:

- Bad probability/range values fail early.
- CLI overrides are visible in the resolved config dump.

### 3. Asset Discovery

- Status: implemented.
- Resolves default roots: `backgrounds`, `foregrounds/landing_foregrounds`, `foregrounds/manometro_foregrounds`.
- Supports custom `backgrounds_dir` as string or list.
- Discovers background images recursively when `paths.recursive_backgrounds` is true.
- Maps foreground filenames to class IDs and class names deterministically.
- Landing class policy is shape/gabarito stem without trailing size digit, for example `estrela`, `estrela_gabarito`, `triangulo`.

Acceptance:

- Discovery returns image paths and class metadata for both dataset types.
- Missing/empty directories produce actionable errors.

### 4. Geometry Utilities

Status: implemented in `imaging.py` and `generator.py`; tests are still pending.

Implement as pure functions with tests:

- Alpha-visible bbox extraction.
- Rectangle overlap with minimum distance.
- Square rotation with expanded canvas.
- Circle/tight rotation with post-rotation alpha bbox crop.
- Background 3x3 tiling.
- Affine matrix sampling/application.
- Shared perspective matrix sampling/application.
- Local foreground bbox to canvas bbox.
- Crop adjustment and YOLO normalization.

Acceptance:

- Rotation tests verify non-transparent pixels remain visible.
- YOLO boxes are normalized and clipped to `[0, 1]`.

### 5. Image-Only Filter Factory

Status: implemented in `filters.py` using AlbumentationsX where available. AlbumentationsX is installed through the `albumentationsx` package and imported with the upstream-compatible `import albumentations as A` module path.

- Build image-only transforms from `background_filters`, `foreground_filters`, and `final_filters`.
- Preserve foreground alpha during image-only foreground filters.
- Keep final filters strictly image-only. No final affine or perspective transforms.

Acceptance:

- Disabled filter groups return identity behavior.
- Foreground alpha is unchanged after image-only filters.

### 6. Background Stage

Status: implemented in `generator.py`.

- Pick a background cell, tile to 3x3, apply background filters, flips/affine transforms, and shared perspective.
- Return generated canvas plus metadata needed for legal centered crop.

Acceptance:

- Generated background can always provide the final crop at requested output size.
- Debug mode can save pre/post stage images.

### 7. Foreground Stage

Status: implemented in `generator.py`.

- Pick foregrounds and apply configured foreground filters, rotation behavior, and shared perspective.
- Return RGBA foreground plus visible bbox and class metadata.
- `manometro` uses square rotation.
- `landing` uses circle/tight rotation.

Acceptance:

- Foreground instances include class IDs.
- Fully transparent or invalid instances are skipped with manifest reason.

### 8. Assembly And Annotation

Status: implemented in `generator.py`.

- Sample final crop before placement.
- Place all foregrounds within crop bounds.
- Enforce optional non-overlap/min-distance constraints.
- Composite foreground layers over background.
- Center crop.
- Generate YOLO `.txt` labels after crop.
- Apply final filters after annotation geometry has been computed.

Acceptance:

- All annotations correspond to visible pasted object regions.
- Multi-instance images produce one label line per placed object.

### 9. Output And Debugging

Status: implemented in `generator.py`.

Output structure:

```text
<output_dir>/
  images/
  labels/
  debug/
  manifest.json
  data.yaml
```

- Debug images should include bbox overlays and optionally stage snapshots for the first `debug` samples.
- Manifest should include source asset paths, sampled parameters, skips, and output filenames.

Acceptance:

- A smoke run with `--num-images 5 --debug 5` writes images, labels, overlays, manifest, and `data.yaml`.

### 10. Performance Pass

- Keep the first implementation single-process.
- Design stage APIs so worker threads/processes can be added later.
- If workers are added, shared perspective parameters must still originate from the orchestrator per image.

Acceptance:

- Single-process run is reproducible with seed.
- Worker mode, if added, does not change class mapping or output schema.

## Open Decisions

- Whether to add a later split/Roboflow export helper. It is not part of the initial core output contract.
- Whether `final_crop_size_range` should support rectangular `[width, height]` and ranged square crops, or only fixed square values in the first implementation.
- Whether to keep local fallback implementations as a future emergency path. Current documented filters are tested against AlbumentationsX with the `albumentationsx>=2.2.4,<2.2.6` pin.
