# Config Schema

The generator config is YAML. The minimal examples in `examples/configs/` are the baseline schema for implementation.

## Top Level

```yaml
dataset_type: manometro
num_images: 10
output_dir: outputs/manometro-minimal
debug: 5
debug_dir: debug
seed: 42
```

- `dataset_type`: `manometro` or `landing`.
- `num_images`: number of final images to generate.
- `output_dir`: root output directory.
- `debug`: number of debug samples to write. Use `0` or `null` to disable.
- `debug_dir`: directory name inside `output_dir`.
- `seed`: run-level random seed.

## Paths

```yaml
paths:
  backgrounds_dir: backgrounds
  foregrounds_dir: foregrounds/manometro_foregrounds
  recursive_backgrounds: true
```

- `backgrounds_dir`: string path or list of paths. Defaults to `backgrounds`.
- `foregrounds_dir`: selected foreground directory.
- `recursive_backgrounds`: discover backgrounds in nested material folders.

Default foreground directories:

- `manometro`: `foregrounds/manometro_foregrounds`
- `landing`: `foregrounds/landing_foregrounds`

## Output

```yaml
output:
  image_size: [1280, 1280]
  image_format: jpg
  label_format: yolo
  write_data_yaml: true
  write_manifest: true
```

- `image_size`: final image size `[width, height]`.
- `image_format`: output extension/encoding.
- `label_format`: currently only `yolo`.
- `write_data_yaml`: write YOLO metadata.
- `write_manifest`: write run manifest.

## Sampling

```yaml
sampling:
  foreground_instances_range: [1, 2]
  foreground_scale_range: [0.20, 0.45]
  min_instance_distance_px: 20
  max_placement_attempts: 50
  final_crop_size_range: [1280, 1280]
```

- `foreground_instances_range`: inclusive `[min, max]` number of objects per image.
- `foreground_scale_range`: foreground width as a fraction of final image width.
- `min_instance_distance_px`: minimum spacing between visible bboxes.
- `max_placement_attempts`: placement retry budget per foreground.
- `final_crop_size_range`: selected crop size before final output. Fixed-size smoke configs use `[1280, 1280]`.

## Perspective

```yaml
perspective_transformations:
  probability: 0.25
  scale_range: [0.0, 0.02]
  shear_range: [-0.015, 0.015]
```

Sample once per generated image. The same sampled transform is applied to background and foreground.

## Background Affine Transformations

```yaml
background_affine_transformations:
  rotation:
    angle_range: [-6, 6]
    probability: 0.35
  scaling:
    scale_range: [0.96, 1.06]
    probability: 0.35
  translation:
    translate_range: [-0.04, 0.04]
    probability: 0.2
```

Background affine transforms are background-only and happen before shared perspective.

## Foreground Affine Transformations

```yaml
foreground_affine_transformations:
  rotation:
    mode: square
    angle_range: [-35, 35]
    probability: 0.8
```

- `mode: square`: expanded-canvas rotation, no tight crop. Use for `manometro`.
- `mode: circle`: expanded-canvas rotation followed by tight visible-alpha crop. Use for `landing`.

## Filters

Filters are stage-separated:

- `background_filters`
- `foreground_filters`
- `final_filters`

Each transform has a `probability` field. Filter names intentionally mirror Albumentations image-only transforms, but the config uses explicit local names such as `hue_shift_range` and `brightness_range` so the app can validate values before constructing Albumentations objects.

Initial supported filters:

- `HueSaturationValue`
- `RandomBrightnessContrast`
- `GaussianBlur`
- `GaussNoise`
- `AdditiveNoise`
- `RandomGamma`
- `PlankianJitter`
- `SaltAndPepper`
- `MotionBlur`
- `PlasmaShadow`
- `PlasmaBrightnessContrast`
- `RandomSunFlare`
- `Illumination`
- `AtmosphericFog`

Unsupported filters should fail config validation rather than being silently ignored.

