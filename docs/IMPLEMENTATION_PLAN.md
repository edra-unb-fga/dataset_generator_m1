# Implementation Plan

## Goal

Develop a new synthetic data generation application from `new implementation snippets/NEW ARCHITECTURE.md`. The application generates YOLO image/label pairs for two dataset types:

- `manometro`: uses `new implementation snippets/foregrounds/manometro_foregrounds`, square rotation behavior.
- `landing`: uses `new implementation snippets/foregrounds/landing_foregrounds`, circle/tight rotation behavior.

The old implementation and the parameter-control example are references for small techniques only. The new app needs its own architecture, config contract, and tests.

## Target Repository Layout

```text
src/
  dataset_generator_m1/
    __init__.py
    __main__.py
    cli.py
    config.py
    models.py
    pipeline.py
    assets.py
    filters.py
    geometry.py
    background.py
    foreground.py
    assembly.py
    annotations.py
    debug.py
    output.py
configs/
  landing.yaml
  manometro.yaml
docs/
  IMPLEMENTATION_PLAN.md
  REFERENCE_NOTES.md
examples/
  configs/
    landing_minimal.yaml
    manometro_minimal.yaml
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
   - Center crop to final image size.
   - Generate YOLO annotations after crop using transformed visible bboxes.
   - Apply final image-only filters.
   - Write image, `.txt` label, manifest row, and optional debug overlays.

## Milestones

### 1. Project Skeleton

- Add package under `src/dataset_generator_m1`.
- Add `pyproject.toml` or `requirements.txt` with pinned-enough dependencies: `albumentations`, `opencv-python`, `numpy`, `pillow`, `pyyaml`, `pydantic` or dataclass validation, and test tooling.
- Add console module entry point through `python -m dataset_generator_m1`.

Acceptance:

- `python -m dataset_generator_m1 --help` works.
- Tests can import package modules.

### 2. Config System

- Define a typed config model matching the architecture doc.
- Support two config files: `configs/landing.yaml` and `configs/manometro.yaml`.
- Merge CLI overrides for `dataset_type`, `config_file`, `num_images`, `output_dir`, `debug`, `debug_dir`, and `backgrounds_dir`.
- Validate ranges and probabilities.

Acceptance:

- Bad probability/range values fail early.
- CLI overrides are visible in the resolved config dump.

### 3. Asset Discovery

- Resolve default asset roots from `new implementation snippets`.
- Support custom `backgrounds_dir` as string or list.
- Map foreground filenames to class IDs and class names deterministically.
- For landing, decide whether `*_gabarito_*` images are their own classes or separate profiles before coding the class map.

Acceptance:

- Discovery returns image paths and class metadata for both dataset types.
- Missing/empty directories produce actionable errors.

### 4. Geometry Utilities

Implement these as pure functions with tests:

- Alpha-visible bbox extraction.
- Square rotation with `expand=True`, preserving full rotated content.
- Circle rotation with post-rotation tight alpha/object crop.
- Background 3x3 tiling.
- Affine transform matrices for background-only transformations.
- Shared perspective matrix sampling and application.
- Bbox transform helpers: local foreground bbox to canvas bbox, crop adjustment, YOLO normalization.

Acceptance:

- Rotation tests verify non-transparent pixels remain visible.
- YOLO boxes are normalized and clipped to `[0, 1]`.

### 5. Albumentations Filter Factory

- Build image-only Albumentations transforms from stage config blocks.
- Keep stage separation:
  - `background_filters`
  - `foreground_filters`
  - `final_filters`
- For RGBA foregrounds, apply filters to RGB and preserve alpha unless the operation is explicitly geometric.
- Do not use Albumentations bbox transforms for final annotations in the first version; final filters must be image-only as specified.

Acceptance:

- Disabled filter groups return identity behavior.
- Foreground alpha is unchanged after image-only filters.

### 6. Background Stage

- Pick a background cell, tile to 3x3, then apply configured background filters, flips, affine transforms, and shared perspective.
- Return generated image plus metadata needed for legal centered crop.

Acceptance:

- Generated background can always provide the final crop at requested output size.
- Debug mode can save pre/post stage images.

### 7. Foreground Stage

- Pick foregrounds and apply configured foreground filters, allowed affine transforms, rotation behavior, and shared perspective.
- Return RGBA foreground plus visible bbox and class metadata.
- `manometro` uses square rotation.
- `landing` uses circle/tight rotation.

Acceptance:

- Foreground instances include class IDs.
- Fully transparent or invalid instances are skipped with manifest reason.

### 8. Assembly And Annotation

- Sample final crop before placement.
- Place all foregrounds within the crop bounds.
- Enforce optional non-overlap/min-distance constraints.
- Composite foreground layers over background.
- Generate YOLO `.txt` labels after crop.
- Apply final filters after annotation generation.

Acceptance:

- All annotations correspond to visible pasted object regions.
- Multi-instance images produce one label line per placed object.

### 9. Output And Debugging

- Output structure:

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

- A smoke run with `--num-images 5 --debug 5` writes images, labels, overlays, and manifest.

### 10. Performance Pass

- Keep the first implementation single-process but design stage APIs so workers can be added cleanly.
- Add thread/process workers only after deterministic smoke tests pass.
- If using threads, shared perspective parameters still originate from the orchestrator per image.

Acceptance:

- Single-process run is reproducible with seed.
- Worker mode, if added, does not change class mapping or output schema.

## Open Decisions

- Exact class map for landing: by shape only, by shape+digit, or separate gabarito classes.
- Whether final output should be flat `images/labels` only or split-ready Roboflow style. The new architecture mentions generated images/annotations, not train/valid/test splits.
- Whether `debug_dir` should always be inside `output_dir` even if the CLI receives an absolute path. The spec says inside output, so default implementation should enforce that.
- Whether `backgrounds_dir` accepts recursive discovery. Default should be recursive because the new snippets background assets are grouped by material folders.

