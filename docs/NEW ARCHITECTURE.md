# Synthetic Dataset Generator Architecture

This document is the product-level architecture for the new generator. It is intentionally self-contained so the old exploratory implementations can be removed after the repository is reorganized. For the expanded pre-rewrite detail, defaults, and filter links, see `docs/ARCHITECTURE_VERBOSE.md`.

The implementation will live in a fresh Python package and will generate YOLO image/label pairs for two dataset families:

- `manometro`: pressure-gauge foregrounds, using square rotation.
- `landing`: landing-marker foregrounds, using circle/tight rotation.

After the repository cleanup, assets are expected at the repository root:

```text
backgrounds/
foregrounds/
  landing_foregrounds/
  manometro_foregrounds/
configs/
examples/
docs/
src/
```

## Pipeline

```text
load config + CLI overrides
-> discover assets
-> sample per-image parameters
-> background generation
-> foreground generation
-> shared perspective transformation
-> assembly
-> center crop
-> YOLO annotation
-> final image-only filters
-> write image, label, manifest, debug output
```

The key geometric rule is that perspective parameters are sampled once per generated image by the orchestrator and then applied to both the foreground and background. This keeps the object and the ground visually coplanar.

## Stage Responsibilities

### Configuration

Each dataset family has its own YAML profile. Config values control image size, crop size, asset paths, foreground count, scale ranges, geometric transform ranges, filter probabilities, and output behavior.

CLI flags may override only explicitly supported top-level values:

- `--dataset-type`
- `--config`
- `--num-images`
- `--output-dir`
- `--debug`
- `--debug-dir`
- `--backgrounds-dir`

Unknown config keys should fail validation with a useful error.

### Background Generation

The background stage:

1. Selects one background texture image.
2. Builds a 3x3 tiled canvas from that selected cell.
3. Applies background image-only filters.
4. Applies background-only affine transforms: rotation, scaling, translation.
5. Applies the shared per-image perspective transform.
6. Returns the transformed canvas and enough metadata for a legal centered crop.

By default, backgrounds are discovered recursively from `backgrounds/`. A custom `backgrounds_dir` may be a path or a list of paths.

### Foreground Generation

The foreground stage:

1. Selects one or more foreground images from the dataset-specific foreground directory.
2. Applies foreground image-only filters with conservative settings.
3. Applies dataset-specific rotation.
4. Applies the shared per-image perspective transform.
5. Returns RGBA foreground images, visible bboxes, class IDs, and transform metadata.

Foreground defaults:

- `manometro`: `foregrounds/manometro_foregrounds`, square rotation.
- `landing`: `foregrounds/landing_foregrounds`, circle/tight rotation.

Foreground filters preserve alpha. Color/noise/blur are applied to RGB pixels and the original alpha mask is kept stable unless a future explicitly geometric foreground transform says otherwise.

### Rotation Modes

`square` rotation:

- Rotate the whole foreground using an expanded canvas.
- Do not crop after rotation.
- The bbox is computed from the visible alpha after rotation.
- Used by `manometro`.

`circle` rotation:

- Rotate the foreground.
- Crop the rotated result back to the tight visible alpha/object bbox.
- Used by `landing`.

Both modes must preserve all visible object pixels.

### Perspective Transformations

Perspective parameters are sampled once per output image from:

```yaml
perspective_transformations:
  probability: 0.25
  scale_range: [0.0, 0.02]
  shear_range: [-0.015, 0.015]
```

If the probability check fails, the identity transform is used. If it succeeds, a single perspective matrix is built and passed to background and foreground generation.

### Assembly

The main orchestrator owns assembly:

1. Sample final crop size before placing foregrounds.
2. Request/generated transformed background and foreground instances.
3. Scale foregrounds using `sampling.foreground_scale_range`.
4. Place all foregrounds inside the selected crop bounds.
5. Enforce minimum distance and retry limits.
6. Composite foreground RGBA layers over the background.
7. Center crop to the configured output size.

Foregrounds that cannot be placed after `max_placement_attempts` are skipped and recorded in the manifest. If an image would end up without valid annotations, the generated image should be skipped unless a future config explicitly allows empty labels.

### Annotation

Annotations are generated after the center crop. This ensures the YOLO boxes match the final image coordinate system.

For each placed object:

1. Use the foreground visible bbox after all foreground geometry.
2. Convert local foreground bbox to assembled canvas coordinates.
3. Adjust coordinates by the final crop origin.
4. Clip to final image bounds.
5. Serialize as YOLO:

```text
<class_id> <cx> <cy> <w> <h>
```

All values after `class_id` are normalized to the final cropped image dimensions.

### Final Transformations

Final filters are image-only and are applied after assembly and annotation geometry is known. They may affect color, lighting, blur, noise, shadows, fog, or similar appearance changes. They must not include affine or perspective transforms.

## Config Shape

The chosen config shape is the one used by the minimal YAML examples in `examples/configs/`. The important structural choice is that image-size and output behavior live under `output`, while generation sampling lives under `sampling`.

```yaml
dataset_type: manometro
num_images: 10
output_dir: outputs/manometro-minimal
debug: 5
debug_dir: debug
seed: 42

paths:
  backgrounds_dir: backgrounds
  foregrounds_dir: foregrounds/manometro_foregrounds
  recursive_backgrounds: true

output:
  image_size: [1280, 1280]
  image_format: jpg
  label_format: yolo
  write_data_yaml: true
  write_manifest: true

sampling:
  foreground_instances_range: [1, 2]
  foreground_scale_range: [0.20, 0.45]
  min_instance_distance_px: 20
  max_placement_attempts: 50
  final_crop_size_range: [1280, 1280]
```

### General Parameters

- `dataset_type`: `manometro` or `landing`.
- `num_images`: number of final images to generate.
- `output_dir`: directory where outputs are written.
- `debug`: integer number of debug samples, or `null`/`0` to disable debug output.
- `debug_dir`: debug directory name inside `output_dir`.
- `seed`: run-level random seed.

### Paths

- `paths.backgrounds_dir`: string path or list of paths. Defaults to `backgrounds`.
- `paths.foregrounds_dir`: foreground directory for the selected dataset.
- `paths.recursive_backgrounds`: when true, discover backgrounds under nested material folders.

### Output

- `output.image_size`: final image size `[width, height]`.
- `output.image_format`: output format, usually `jpg`.
- `output.label_format`: currently `yolo`.
- `output.write_data_yaml`: write YOLO class metadata.
- `output.write_manifest`: write run manifest with generated files, source assets, sampled params, and skips.

### Sampling

- `sampling.foreground_instances_range`: inclusive `[min, max]` number of objects per generated image.
- `sampling.foreground_scale_range`: foreground size range as a fraction of final image width.
- `sampling.min_instance_distance_px`: minimum pixel distance between placed visible bboxes.
- `sampling.max_placement_attempts`: retry budget per foreground instance.
- `sampling.final_crop_size_range`: `[min, max]` or fixed `[size, size]` crop size. For square 1280 output, use `[1280, 1280]`.

### Geometry

- `perspective_transformations`: shared per-image perspective settings.
- `background_affine_transformations`: background-only rotation, scaling, translation.
- `foreground_affine_transformations.rotation`: foreground rotation mode, range, and probability.

### Filters

Filters are grouped by stage:

- `background_filters`
- `foreground_filters`
- `final_filters`

Each filter entry has Albumentations-like parameter names plus a `probability`. The implementation should build image-only Albumentations transforms from these config blocks when Albumentations exposes a compatible transform, with documented local fallbacks only where necessary.

Supported initial filters:

- Background: `HueSaturationValue`, `RandomBrightnessContrast`, `GaussianBlur`, `GaussNoise`.
- Foreground: `HueSaturationValue`, `AdditiveNoise`, `PlasmaShadow`, `PlasmaBrightnessContrast`, `RandomSunFlare`.
- Final: `RandomGamma`, `PlanckianJitter`, `SaltAndPepper`, `MotionBlur`, `PlasmaShadow`, `PlasmaBrightnessContrast`, `RandomSunFlare`, `Illumination`, `AtmosphericFog`.

## CLI

Target CLI:

```powershell
python -m dataset_generator_m1 generate --dataset-type manometro --config configs/manometro.yaml --num-images 50 --output-dir outputs/manometro-smoke --debug 10
```

The CLI should print or write a resolved config summary so smoke runs are auditable.

## Output Structure

```text
<output_dir>/
  images/
    image_000000.jpg
  labels/
    image_000000.txt
  debug/
    image_000000_overlay.jpg
  data.yaml
  manifest.json
```

`data.yaml` stores class names and paths in YOLO-compatible form. `manifest.json` stores source image paths, class choices, sampled transform parameters, placement attempts, skip reasons, and output paths.

## Implementation Notes Preserved From Prototypes

The following prototype behaviors are part of this architecture now and no longer depend on the old folders:

- Use alpha-threshold visible bbox extraction for RGBA foregrounds.
- Use rectangle overlap checks with configurable minimum distance during placement.
- Preserve alpha while applying image-only foreground filters.
- Keep CLI/config merging explicit and limited to supported override fields.
- Emit a manifest/summary file for run inspection.
- Seed the run once and derive per-image random state from that seed.
- Keep Roboflow-style split export out of the initial core. The first output contract is flat `images/`, `labels/`, `debug/`, `data.yaml`, and `manifest.json`.
