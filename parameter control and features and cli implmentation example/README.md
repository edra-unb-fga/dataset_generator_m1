# ImgAug Augmentation Pipeline

Parametric, YOLO-oriented image augmentation pipeline built with `imgaug`.

This repository focuses on **dataset expansion with annotation-safe transforms** for object detection workflows, including support for both:

- YOLO bounding boxes (`class cx cy w h`)
- YOLO polygon-style annotations (`class x1 y1 x2 y2 ...`)

The implementation is in `src/augmentation_pipeline.py`, and the augmentation recipe is driven by YAML files in `configs/`.

---

## What this project does

Given an input dataset and a config profile, the pipeline:

1. Discovers dataset splits (`train`, `val`, `test`) from `data.yaml` / `dataset.yaml` or folder conventions.
2. Builds a stochastic `imgaug` sequence from YAML parameters.
3. Applies deterministic-per-sample augmentation to image + annotations together.
4. Clips and validates transformed annotations (drops invalid/too-small overlaps).
5. Writes augmented dataset back in YOLO folder structure.
6. Produces a `manifest.json` report with processed/written/skipped counters.

---

## Repository map

- `src/augmentation_pipeline.py` — main CLI + augmentation engine.
- `configs/default.yaml` — baseline augmentation profile.
- `configs/default_lipobag.yaml` — stronger profile tuned for Lipobag experiments.
- `docs/augmentation_pipeline_spec.md` — design/spec reference.
- `.github/AGENTS.md` — project working conventions and implementation notes.
- `requirements.txt` — Python dependency list for reproducible setup.
- `outputs/` — example generated datasets from previous runs.

---

## Requirements

Python 3.10+ recommended.

Install dependencies from the repository root with:

`pip install -r requirements.txt`

---

## Input dataset expectations

The pipeline expects YOLO-style image/label pairing. It supports common layouts:

### Split layout

```
<dataset_root>/
  train/
    images/
    labels/
  val/
    images/
    labels/
  test/
    images/
    labels/
```

### Flat layout fallback

```
<dataset_root>/
  images/
  labels/
```

### Metadata discovery

If present, `data.yaml` or `dataset.yaml` is used to resolve split paths. If not, folder conventions above are used.

---

## How to run

### Quickstart (new environment)

Use this flow from repository root:

1. Create and activate a virtual environment.
2. Install dependencies from `requirements.txt`.
3. Run a small smoke augmentation.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/augmentation_pipeline.py -c configs/default.yaml -i pre_augmentation_separated_dataset -o outputs/augmented-smoke --split train --limit 20 --seed 42 --manifest
```

If your shell blocks script activation, either allow local scripts in your profile/session or activate the environment using your preferred shell method.

From repository root, run:

`python src/augmentation_pipeline.py --config configs/default.yaml --input <DATASET_ROOT> --output <OUTPUT_ROOT>`

### CLI arguments

- `--config, -c` (optional): YAML config path (default: `configs/default.yaml`)
- `--input, -i` (required): input dataset root
- `--output, -o` (required): output dataset root
- `--split` (optional): `train | val | test | all`
- `--limit` (optional): max source images per split (debugging/smoke runs)
- `--seed` (optional): random seed override
- `--manifest` (optional flag): force writing `manifest.json`

### Example: quick smoke run

`python src/augmentation_pipeline.py -c configs/default.yaml -i pre_augmentation_separated_dataset -o outputs/augmented-smoke --split train --limit 20 --seed 42 --manifest`

### Example: Lipobag profile

`python src/augmentation_pipeline.py -c configs/default_lipobag.yaml -i pre_augmentation_separated_dataset -o outputs/augmented-lipobag-custom --split all --manifest`

---

## Output structure

Generated dataset mirrors YOLO split structure:

```
<output_root>/
  manifest.json
  train/
    images/
    labels/
    debug/   # optional, if debug_preview > 0
  val/
    images/
    labels/
  test/
    images/
    labels/
```

Behavior controlled by config:

- `aio.keep_original`: copy original sample into output too
- `aio.augmentations_per_image`: number of variants per source image
- `aio.allow_empty`: whether to keep samples with all annotations dropped
- `aio.min_bbox_iou`: minimum retained overlap ratio after transform
- `aio.debug_preview`: number of visualization images with overlayed boxes/polygons

> Note: the code accepts either `io:` or `aio:` in config files.

---

## Understanding the parametric imgaug design

The sequence is intentionally **parametric and composable**. YAML groups map to transformation families:

- `augment.core`
  - `flip_lr`, `flip_ud`, `crop_percent`, `contrast`
- `augment.geometric`
  - probabilistic affine + perspective bundle
- `augment.texture_noise`
  - `blurs` and `perturb` sampled via `SomeOf`
  - includes Gaussian noise, dropout, cutout, brightness shifts
- `augment.color`
  - multiply, hue/saturation, grayscale blending
- `augment.segmentation.uniform_voronoi`
  - optional Voronoi-based stylization

This structure is the key to creating your own pipeline recipes: each block can be tuned independently in probability and intensity.

---

## Create your own augmentation profile (recommended workflow)

1. Copy `configs/default.yaml` to `configs/my_profile.yaml`.
2. Start conservative:
   - reduce aggressive ranges (`crop_percent`, `rotate`, `perspective_scale`)
   - keep `min_bbox_iou` stricter (e.g., `0.15` to `0.30`)
3. Run on a small subset:
   - `--split train --limit 30`
4. Inspect `debug/` previews and skipped reasons in `manifest.json`.
5. Increase one group at a time:
   - geometric first
   - then blur/noise
   - then color/stylization
6. Track downstream training metrics before broad rollout.

### Practical tuning heuristics

- If too many labels are dropped: lower transform intensity or lower `min_bbox_iou` slightly.
- If images become unrealistic: reduce `SomeOf` counts and probability (`prob`) in `texture_noise` and `color`.
- If model overfits: increase diversity via `augmentations_per_image` and broaden mild transforms.
- If tiny objects disappear: reduce cropping and strong perspective transforms.

---

## Annotation handling details

- Bounding boxes are converted to `imgaug` bounding boxes, transformed, then clipped.
- Polygon annotations are transformed through `imgaug` polygons and serialized back to YOLO polygon lines.
- Annotations with invalid geometry or insufficient retained area are discarded.
- If all annotations are dropped and `allow_empty` is `false`, that augmented sample is skipped.

This keeps outputs safer for training than naive image-only augmentation.

---

## Reproducibility notes

- Set `--seed` (or `defaults.seed`) for reproducible random sampling.
- Sequence order includes randomization (`random_order=True`), so fixed seeds matter.
- Use low `--limit` smoke runs to validate profile changes before full dataset generation.

---

## Known gaps vs. spec

The spec mentions worker parallelism (`--workers`), but current CLI implementation in `src/augmentation_pipeline.py` does **not** expose or execute multiprocessing yet. The pipeline currently runs in-process.

---

## Next ideas (if you want to evolve this repo)

- Pin exact dependency versions after first stable baseline run.
- Add unit tests for annotation conversions and config parsing.
- Add true worker-based parallel execution.
- Add an interactive preview notebook for rapid policy tuning.

---

If you want, I can also generate a **profile cookbook** next (e.g., `configs/profiles/` with mild, balanced, aggressive presets) so users can pick policies by scenario with minimal trial-and-error.