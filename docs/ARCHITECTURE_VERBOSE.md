# Verbose Architecture Reference

This document preserves the full design intent from the pre-rewrite architecture notes, updated to the current config structure. It is the long-form reference for implementation decisions, defaults, and stage behavior.

## Pipeline Summary

The generator creates synthetic YOLO datasets through this sequence:

```text
configuration
-> asset discovery
-> per-image parameter sampling
-> background generation
-> foreground generation
-> shared perspective transformation
-> assembly
-> center crop
-> YOLO annotation
-> final image-only transformations
-> output writing
```

The key visual requirement is coplanarity: the same sampled perspective transform must be applied to background and foreground for a given image. The background represents the plane, and the foreground objects are treated as sitting on that plane.

## Default Asset Layout

After repository cleanup, assets should be rooted directly in the repo:

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

Default paths:

- Backgrounds: `backgrounds`
- Landing foregrounds: `foregrounds/landing_foregrounds`
- Manometro foregrounds: `foregrounds/manometro_foregrounds`

Background discovery should be recursive by default because backgrounds are grouped by material category.

## Configuration Philosophy

All relevant variables must be controlled by YAML:

- Filter application probabilities.
- Filter value ranges.
- Affine transform ranges.
- Shared perspective ranges.
- Output image size.
- Final crop size.
- Foreground scale.
- Foreground instance count.
- Object spacing and placement retry budget.
- Output behavior.
- Debug behavior.

There should be one normal config per dataset family:

- `configs/manometro.yaml`
- `configs/landing.yaml`

The `examples/configs/` files are small smoke profiles that document the schema in executable form.

## Canonical Config Shape

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

## Defaults

These are the implementation defaults when a value is omitted. Dataset-specific configs may intentionally override them.

### Top-Level Defaults

| Key | Default | Notes |
| --- | --- | --- |
| `dataset_type` | `manometro` | CLI can override with `--dataset-type`. |
| `num_images` | `10` | Smoke-safe default. |
| `output_dir` | `outputs/generated` | Must be created if missing. |
| `debug` | `0` | `0` or `null` disables debug output. |
| `debug_dir` | `debug` | Always interpreted inside `output_dir`. |
| `seed` | `42` | Run-level seed. |

### Path Defaults

| Key | Default | Notes |
| --- | --- | --- |
| `paths.backgrounds_dir` | `backgrounds` | String or list of paths. |
| `paths.foregrounds_dir` | Dataset-specific | `foregrounds/manometro_foregrounds` or `foregrounds/landing_foregrounds`. |
| `paths.recursive_backgrounds` | `true` | Discover nested material folders. |

### Output Defaults

| Key | Default | Notes |
| --- | --- | --- |
| `output.image_size` | `[1280, 1280]` | `[width, height]`. |
| `output.image_format` | `jpg` | Initial supported output format. |
| `output.label_format` | `yolo` | Initial supported label format. |
| `output.write_data_yaml` | `true` | Writes class metadata. |
| `output.write_manifest` | `true` | Writes run manifest. |

### Sampling Defaults

| Key | Default | Notes |
| --- | --- | --- |
| `sampling.foreground_instances_range` | `[1, 2]` | Inclusive object count range. |
| `sampling.foreground_scale_range` | `[0.20, 0.45]` | Foreground width fraction of final image width. |
| `sampling.min_instance_distance_px` | `20` | Minimum distance between visible bboxes. |
| `sampling.max_placement_attempts` | `50` | Retry budget per foreground instance. |
| `sampling.final_crop_size_range` | `[1280, 1280]` | Fixed square crop for baseline profiles. |

### Perspective Defaults

| Key | Default | Notes |
| --- | --- | --- |
| `perspective_transformations.probability` | `0.25` | Probability of non-identity shared perspective. |
| `perspective_transformations.scale_range` | `[0.0, 0.02]` | Perspective strength range. |
| `perspective_transformations.shear_range` | `[-0.015, 0.015]` | Shear/tilt range. |

### Background Affine Defaults

| Key | Default |
| --- | --- |
| `background_affine_transformations.rotation.angle_range` | `[-6, 6]` |
| `background_affine_transformations.rotation.probability` | `0.35` |
| `background_affine_transformations.scaling.scale_range` | `[0.96, 1.06]` |
| `background_affine_transformations.scaling.probability` | `0.35` |
| `background_affine_transformations.translation.translate_range` | `[-0.04, 0.04]` |
| `background_affine_transformations.translation.probability` | `0.2` |

### Foreground Affine Defaults

| Key | Manometro Default | Landing Default |
| --- | --- | --- |
| `foreground_affine_transformations.rotation.mode` | `square` | `circle` |
| `foreground_affine_transformations.rotation.angle_range` | `[-35, 35]` | `[-180, 180]` |
| `foreground_affine_transformations.rotation.probability` | `0.8` | `1.0` |

## Stage Details

### Background Generation

Background generation uses tiling to create a larger texture canvas. The selected background image becomes the center cell and its eight neighbors, giving a 3x3 canvas. The larger canvas gives rotation, translation, perspective, and final cropping room without exposing empty borders.

Background stage order:

1. Choose background image.
2. Convert to RGB/RGBA as needed.
3. Tile to 3x3.
4. Apply background image-only filters.
5. Apply configured horizontal/vertical flip support if implemented in affine utilities.
6. Apply background affine transforms.
7. Apply shared perspective transform sampled by the orchestrator.
8. Return canvas and crop metadata.

### Foreground Generation

Foreground generation uses pre-rendered PNG assets with transparency. Foreground filters must be conservative: no flips in the baseline, small blur/noise, stable alpha, and rotation methods that preserve all visible content.

Foreground stage order:

1. Choose foreground asset.
2. Convert to RGBA.
3. Apply image-only foreground filters to RGB while preserving alpha.
4. Rotate using dataset-specific mode.
5. Apply shared perspective transform.
6. Compute visible bbox from alpha.
7. Return transformed foreground, bbox, class ID, source path, and transform metadata.

### Rotation Methods

Square rotation:

- Used for `manometro`.
- Rotate with expanded canvas.
- Do not crop after rotation.
- Compute bbox from visible alpha.
- Keeps the larger bounding canvas when necessary to preserve square-like object extent.

Circle/tight rotation:

- Used for `landing`.
- Rotate with expanded canvas.
- Compute visible alpha bbox.
- Crop back to the tight bbox.
- Recompute local bbox after crop.
- Keeps a tight object box for circular/landing-marker objects.

### Perspective Transformations

Perspective transformation is shared per image. The orchestrator samples one transform state, then gives it to background and foreground generation. If the probability check fails, use identity transform and record that in the manifest.

The implementation may use OpenCV perspective matrices. The important contract is not the exact math helper; it is that the same sampled parameters are used consistently for all surfaces in a generated image.

### Assembly

The main orchestrator owns assembly because it has access to the final crop, transformed background, foreground instances, placement constraints, and annotation metadata.

Assembly rules:

- Sample the final crop size before foreground placement.
- Place foregrounds only where their visible bbox is contained in the crop.
- Respect `sampling.min_instance_distance_px`.
- Try up to `sampling.max_placement_attempts`.
- Composite RGBA foregrounds over the background.
- Skip instances that cannot be placed.
- Skip final images that would have no valid labels.

### Annotation

Annotations are generated after the center crop because this is the image actually written to disk.

For each foreground:

1. Start from the local visible bbox.
2. Transform it into assembled canvas coordinates using placement information.
3. Shift it by final crop origin.
4. Clip to final image bounds.
5. Drop invalid or empty boxes.
6. Normalize by final image width and height.
7. Serialize as YOLO.

YOLO line format:

```text
<class_id> <cx> <cy> <w> <h>
```

Use six decimal places for deterministic text output.

### Final Transformations

Final filters affect the whole assembled and cropped image. They may change appearance only:

- Color.
- Contrast.
- Brightness.
- Saturation.
- Blur.
- Noise.
- Highlights.
- Shadows.
- Fog.
- Illumination.

Final filters must not include affine, perspective, crop, or bbox-changing transforms.

## Filter Defaults And Documentation Links

The examples comment each augmentation block with a documentation link. The initial filter defaults are:

### Background Filters

`HueSaturationValue`: https://explore.albumentations.ai/transform/HueSaturationValue

- `hue_shift_range`: `[-6, 6]`
- `sat_shift_range`: `[-18, 18]`
- `val_shift_range`: `[-12, 12]`
- `probability`: `0.3`

`RandomBrightnessContrast`: https://explore.albumentations.ai/transform/RandomBrightnessContrast

- `brightness_range`: `[-0.12, 0.12]`
- `contrast_range`: `[-0.12, 0.12]`
- `brightness_by_max`: `true`
- `ensure_safe_output`: `true`
- `probability`: `0.4`

`GaussianBlur`: https://explore.albumentations.ai/transform/GaussianBlur

- `blur_range`: `[3, 5]`
- `sigma_range`: `[0.0, 0.6]`
- `probability`: `0.15`

`GaussNoise`: https://explore.albumentations.ai/transform/GaussNoise

- `std_range`: `[0.0, 0.06]`
- `mean_range`: `[0.0, 0.0]`
- `per_channel`: `false`
- `probability`: `0.2`

### Foreground Filters

`HueSaturationValue`: https://explore.albumentations.ai/transform/HueSaturationValue

- `hue_shift_range`: `[-3, 3]`
- `sat_shift_range`: `[-8, 8]`
- `val_shift_range`: `[-6, 6]`
- `probability`: `0.2`

`AdditiveNoise`: https://explore.albumentations.ai/transform/AdditiveNoise

- `noise_type`: `gaussian`
- `spatial_mode`: `shared`
- `noise_params`: `null`
- `probability`: `0.1`

`PlasmaShadow`: https://explore.albumentations.ai/transform/PlasmaShadow

- `shadow_intensity_range`: `[0.1, 0.35]`
- `plasma_size`: `256`
- `roughness`: `3.0`
- `probability`: `0.0`

`PlasmaBrightnessContrast`: https://explore.albumentations.ai/transform/PlasmaBrightnessContrast

- `brightness_range`: `[-0.08, 0.08]`
- `contrast_range`: `[-0.08, 0.08]`
- `plasma_size`: `256`
- `roughness`: `3.0`
- `probability`: `0.0`

`RandomSunFlare`: https://explore.albumentations.ai/transform/RandomSunFlare

- `flare_roi`: `[0.0, 0.0, 1.0, 0.5]`
- `src_radius`: `80`
- `src_color`: `[255, 255, 255]`
- `angle_range`: `[0.0, 1.0]`
- `num_flare_circles_range`: `[1, 3]`
- `method`: `overlay`
- `probability`: `0.0`

### Final Filters

`RandomGamma`: https://explore.albumentations.ai/transform/RandomGamma

- `gamma_range`: `[90, 110]`
- `probability`: `0.2`

`PlanckianJitter`: https://explore.albumentations.ai/transform/PlanckianJitter

- `mode`: `blackbody`
- `temperature_range`: `[5000, 8500]`
- `sampling_method`: `uniform`
- `probability`: `0.1`

`SaltAndPepper`: https://explore.albumentations.ai/transform/SaltAndPepper

- `amount_range`: `[0.0, 0.01]`
- `salt_vs_pepper_range`: `[0.45, 0.55]`
- `probability`: `0.0`

`MotionBlur`: https://explore.albumentations.ai/transform/MotionBlur

- `blur_range`: `[3, 5]`
- `allow_shifted`: `true`
- `angle_range`: `[0, 12]`
- `direction_range`: `[-0.2, 0.2]`
- `probability`: `0.1`

`PlasmaShadow`: https://explore.albumentations.ai/transform/PlasmaShadow

- `shadow_intensity_range`: `[0.1, 0.35]`
- `plasma_size`: `256`
- `roughness`: `3.0`
- `probability`: `0.0`

`PlasmaBrightnessContrast`: https://explore.albumentations.ai/transform/PlasmaBrightnessContrast

- `brightness_range`: `[-0.08, 0.08]`
- `contrast_range`: `[-0.08, 0.08]`
- `plasma_size`: `256`
- `roughness`: `3.0`
- `probability`: `0.0`

`RandomSunFlare`: https://explore.albumentations.ai/transform/RandomSunFlare

- `flare_roi`: `[0.0, 0.0, 1.0, 0.5]`
- `src_radius`: `80`
- `src_color`: `[255, 255, 255]`
- `angle_range`: `[0.0, 1.0]`
- `num_flare_circles_range`: `[1, 3]`
- `method`: `overlay`
- `probability`: `0.0`

`Illumination`: https://explore.albumentations.ai/transform/Illumination

- `mode`: `linear`
- `intensity_range`: `[0.01, 0.12]`
- `effect_type`: `both`
- `angle_range`: `[0, 360]`
- `center_range`: `[0.25, 0.75]`
- `sigma_range`: `[0.2, 0.6]`
- `probability`: `0.0`

`AtmosphericFog`: https://explore.albumentations.ai/transform/AtmosphericFog

- `density_range`: `[0.05, 0.15]`
- `fog_color`: `[255, 255, 255]`
- `depth_mode`: `linear`
- `probability`: `0.0`

## CLI

Target CLI:

```powershell
python -m dataset_generator_m1 generate --dataset-type manometro --config configs/manometro.yaml --num-images 50 --output-dir outputs/manometro-smoke --debug 10
```

Supported overrides:

- `--dataset-type`
- `--config`
- `--num-images`
- `--output-dir`
- `--debug`
- `--debug-dir`
- `--backgrounds-dir`

The CLI should write a resolved config summary into `manifest.json`.

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

## Implementation Details Preserved From Prototypes

- Use alpha-threshold visible bbox extraction for foreground bboxes.
- Preserve RGBA alpha during foreground image-only filters.
- Use simple rectangle overlap checks with minimum distance.
- Place objects by retrying random legal positions inside the selected crop.
- Use explicit CLI override merging rather than arbitrary deep override syntax.
- Write a manifest instead of relying on console logs.
- Seed once at run level and derive per-image random state.
- Keep train/valid/test or Roboflow-style export out of the first core implementation.




