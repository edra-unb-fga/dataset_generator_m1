# Preserved Prototype Knowledge

This file captures the implementation details that are worth keeping before the prototype/reference folders are deleted. It intentionally describes the behavior directly instead of pointing back to those folders.

## Alpha-Visible Bounding Boxes

RGBA foregrounds should use the alpha channel to compute the visible object bbox.

Algorithm:

1. Read the alpha channel as a 2D array.
2. Select pixels where `alpha > alpha_threshold`.
3. If no pixels are visible, treat the foreground as invalid.
4. Otherwise:
   - `x1 = min(visible_x)`
   - `y1 = min(visible_y)`
   - `x2 = max(visible_x) + 1`
   - `y2 = max(visible_y) + 1`

Use a small default threshold such as `8` to ignore near-transparent edges.

## Rectangle Overlap With Distance

Placement should reject objects that overlap or sit too close to already placed objects.

For rectangles `(x, y, w, h)`, compute right/bottom as `x + w`, `y + h`. Two rectangles do not conflict when one is fully left, right, above, or below the other by at least `min_instance_distance_px`. Otherwise they conflict.

This is intentionally simple and deterministic. It is good enough for initial placement and easy to test.

## Multi-Object Placement Loop

For each selected foreground:

1. Apply rotation and foreground-local transformations.
2. Scale the foreground based on `sampling.foreground_scale_range`.
3. Compute the visible bbox after scale.
4. Try random positions inside the selected crop bounds.
5. Reject positions that fail containment or minimum-distance checks.
6. Stop after `sampling.max_placement_attempts`.
7. If placement fails, skip that instance and write a manifest reason.

The final annotation uses the visible bbox, not the full transparent foreground canvas.

## YOLO Serialization

YOLO label lines use:

```text
<class_id> <cx> <cy> <w> <h>
```

Where `cx`, `cy`, `w`, and `h` are normalized by final cropped image width/height. Use six decimal places for stable text output.

Conversion from pixel bbox:

```text
cx = (x1 + x2) / 2 / image_width
cy = (y1 + y2) / 2 / image_height
w = (x2 - x1) / image_width
h = (y2 - y1) / image_height
```

Clip boxes to image bounds before serialization and drop boxes with non-positive width or height.

## Foreground Alpha Preservation

Image-only filters should not accidentally make transparent regions visible.

Recommended behavior for RGBA foregrounds:

1. Split foreground into RGB and alpha.
2. Apply image-only filters to RGB.
3. Recombine filtered RGB with the original alpha.
4. For pixels where alpha is zero, force RGB to zero as a cleanup step.

This allows color/noise/blur on the visible object without polluting transparent padding.

## Rotation Modes

Square rotation:

- Rotate with expanded canvas.
- Do not crop after rotation.
- Compute bbox from visible alpha after rotation.
- Use for `manometro`.

Circle/tight rotation:

- Rotate with expanded canvas.
- Compute visible alpha bbox.
- Crop the rotated image to that visible bbox.
- Recompute local bbox in cropped coordinates.
- Use for `landing`.

Both modes should use high-quality resampling and preserve all visible pixels.

## Balanced Class Sampling

For datasets with a small finite set of foreground classes, use shuffled cycles to avoid long random droughts for any class:

1. Build all class candidates.
2. Shuffle the list.
3. Draw from it in order.
4. When exhausted, reshuffle and continue.
5. For multi-object images, avoid selecting the same candidate twice when possible.

This is optional for the first smoke implementation but useful once class mapping is final.

## Config And CLI Merging

Use this precedence:

```text
defaults in code
-> YAML config
-> explicit CLI overrides
```

Only supported CLI flags should override config values. Do not implement arbitrary deep overrides in the first version; it makes validation and reproducibility harder.

The run should write a resolved config summary into the manifest or next to it.

## Manifest

Write `manifest.json` when `output.write_manifest` is true. Include:

- Resolved config.
- Seed.
- Class map.
- Generated image count.
- Skipped image/instance count.
- Per-image source background.
- Per-image foreground source files and class IDs.
- Sampled affine/perspective/filter parameters when available.
- Placement attempts and skip reasons.
- Output image and label paths.

This replaces console-only progress logs and makes smoke runs inspectable after the fact.

## Output Contract

Initial output should be flat and YOLO-compatible:

```text
<output_dir>/
  images/
  labels/
  debug/
  data.yaml
  manifest.json
```

Train/valid/test splitting and Roboflow-style export can be added later as a separate export command.

## Image Loading Normalization

When reading images:

- Convert backgrounds to RGB or RGBA as needed for compositing.
- Convert foregrounds to RGBA.
- If an input has grayscale or unusual channels, normalize to expected channel count before processing.
- Keep output image dtype as `uint8`.

## Error Handling

Prefer structured skip records over crashes for per-sample failures:

- Missing foreground/background files: fatal startup error.
- Fully transparent foreground: skip instance.
- Could not place an object: skip instance.
- Generated image has no labels: skip image.
- Invalid config values: fatal startup error.

