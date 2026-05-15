# Reference Notes

## New Architecture Requirements

The new application is a staged synthetic generation pipeline:

```text
background + foreground generation
-> shared perspective transformations
-> assembly + YOLO annotation
-> final image-only transformations
-> center crop
-> final image
```

Important constraints:

- Config must control probabilities, ranges, object counts, foreground scale, crop ranges, and stage filters.
- There must be separate configs for `manometro` and `landing`.
- Albumentations should be used for image-only filters.
- Affine transformations, perspective transformations, crop, assembly, and bbox math can use OpenCV/Pillow/local geometry.
- Perspective parameters are sampled once per image and applied to both foreground and background.
- Foregrounds must be placed so they remain inside the selected final crop.
- YOLO annotations are generated after the crop from pipeline metadata and placement information.

## Useful Old Implementation Ideas

From `old implementation/modules/modulo_composicao.py`:

- `_get_visible_bbox` computes a tight bbox from foreground alpha using a small alpha threshold.
- `_check_overlap` is a simple rectangle overlap test with a minimum distance.
- `compose_multiple` shows the core placement loop: sample scale, resize, attempt placement, paste with alpha, then serialize YOLO.

Do not port this directly because the new pipeline needs preselected crop bounds, shared perspective, and stage-separated filters.

From `old implementation/modules/modulo_augmentation_imgaug.py`:

- Image-only foreground augmentation should preserve the alpha channel.
- Bounding-box conversion helpers are useful conceptually, but the new app should keep final filters image-only and own the geometry path.

From `old implementation/main.py`:

- Balanced class selection is useful for landing if the class map uses shape+digit combinations.
- Roboflow export can be a later helper, not the first output contract unless requested.

## Useful Parameter-Control Example Ideas

From `parameter control and features and cli implmentation example/src/augmentation_pipeline.py`:

- `argparse` plus YAML config loading is a reasonable CLI baseline.
- Config merging should be explicit and limited to declared CLI override fields.
- A manifest/summary JSON is useful for run inspection.
- Deterministic seeds should be set once at the run level and propagated through sampled per-image parameters.

Do not reuse the `imgaug` implementation. The new spec calls for Albumentations image-only transforms and local geometry for perspective/annotation.

## Rotation Behavior

Two rotation modes should be encoded explicitly:

- `square`: rotate the full foreground with expanded canvas. Use this for `manometro`.
- `circle`: rotate, then crop to the tight visible alpha/object bbox. Use this for `landing`.

Both modes should return:

- RGBA image.
- Local visible bbox after rotation/crop.
- Transform metadata for debugging and manifest entries.

## Annotation Rules

YOLO line format:

```text
<class_id> <cx> <cy> <w> <h>
```

All coordinates are normalized against the final cropped image dimensions. Bboxes should be derived from visible alpha/object bounds after all geometric transforms and placement. Clip boxes to image bounds and skip invalid boxes.

## Asset Notes

Default assets live under `new implementation snippets`:

- Backgrounds: recursive material folders under `backgrounds`.
- Landing foregrounds: `foregrounds/landing_foregrounds`.
- Manometro foregrounds: `foregrounds/manometro_foregrounds`.

Filename parsing should be deterministic and tested. The class map should be written into `data.yaml` and the manifest.

