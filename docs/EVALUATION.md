# Offline evaluation and reference evidence

These commands evaluate **external predictions**. They do not train, load a model, run inference, fit
camera calibration or demonstrate that a synthetic treatment helps on real images.

```sh
uv sync --locked --extra dev --extra evaluation
uv run python -m dataset_generator_m1 evaluate prepare --manifest examples/evaluation/pool.json --output-dir outputs/evaluation/dataset --output-format json
uv run python -m dataset_generator_m1 evaluate score --dataset outputs/evaluation/dataset --predictions outputs/evaluation/predictions.json --output-dir outputs/evaluation/score --output-format json
uv run python -m dataset_generator_m1 evaluate compare --left outputs/evaluation/score-a --right outputs/evaluation/score-b --output-dir outputs/evaluation/comparison --output-format json
```

Change the example's `source` to your existing pool. Input manifests resolve source/binding paths
relative to the manifest; image and annotation paths stay inside their declared roots. Output
directories must be empty. Reports are portable `index.html` plus JSON and relative image artifacts.
JSON commands print exactly one result/error document. Base generation/CLI imports need no evaluation
extra; its absence gives an installation message when scoring or decoding masks is requested.

## Dataset and prediction contracts

Evaluation manifest schema v1 selects `format: coco|pool|yolo-export`, explicit `domain: real|synthetic`
and `role: development|held-out|regression`. Pool/export sources are known synthetic and cannot be
declared real. `annotation_semantics: visible|full|unknown` describes the reference policy; pool masks
require a known policy. A declared export policy must match unbound segmentation labels.

- COCO: `source` root, `ground_truth` JSON filename and optional `images_root` relative to that root.
  Ground-truth annotation IDs must be **positive**; image/category zero is permitted. Preserve crowd
  semantics. Pixel boxes are COCO xywh with no inclusive-coordinate +1.
- Pool: `source` is an inspected pool. Primary segmentation truth is the exact thresholded coverage,
  not YOLO polygon reconstruction. The full/visible choice is explicit.
- Repository YOLO export: select `split`; optional `pool_bindings: {pool-000: relative/pool}` verifies
  original run hashes and exported image bytes before recovering exact masks and sampled conditions.
  Without bindings the report explicitly identifies exported-label truth and retains fidelity warnings.
  This is not an arbitrary third-party YOLO prediction parser or a general COCO export command.

Prepared `dataset.json` contains immutable copied images, canonical ground truth, exact content hashes,
class/image IDs, declared policies, lineage, optional metadata and `dataset_sha256`. Optional
`metadata_file` maps prepared integer image IDs (as strings) to declared conditions such as
`capture_session`, `location`, `lighting` and `material`. Unknown values remain unknown. Synthetic
recipe/effect/projection/clipping/occlusion evidence is retained separately from measured real conditions.

A prediction coverage manifest is separate from its COCO result array:

```json
{"schema_version":1,"dataset_sha256":"<copy the actual dataset hash>","predictions":"results.json","image_ids":[1,2],"model":{"id":"external-model","checkpoint_sha256":"<actual hash or explicitly unknown>"}}
```

`image_ids` enumerates every processed image, including negatives and images with no predictions.
Missing coverage is rejected unless `allow_partial: true`; partial coverage remains explicit and cannot
be compared to a full-coverage score. COCO results supply `image_id`, `category_id`, `score`, pixel
`bbox` for box scoring and image-sized RLE `segmentation` for mask scoring. The canonical dataset may
also supply valid COCO polygons. Compressed/uncompressed RLE must cover the image exactly before
native decoding. Scores are finite [0,1], boxes positive/in-frame, and unknown IDs fail validation.

Default `--tasks bbox segm` computes canonical COCO AP/AR, with absent-support scores represented by
null. `--tasks bbox` supports detection-only annotations. Diagnostics use the canonical crowd-aware
matcher at `--confidence 0.25 --iou 0.50`; these counts are distinct from all-threshold AP. Canonical
limits are recorded. Overlays are bounded and labeled; no matching or metric code is reimplemented.

Comparison checks dataset/coverage/category/task/policy/scorer identities. A matching hash does not
prove controlled training or capture independence: inspect training provenance, repeated seeds and
capture-session/location separation before causal claims. Pixel-size metrics are not physical scale;
sampled projective geometry is not measured camera tilt. The historical `visible_bbox_fraction` is a
clipping bbox ratio, not a mask-area occlusion measurement.

## Reference audit and supplied-camera checks

```sh
uv run python -m dataset_generator_m1 reference audit --manifest examples/reference/artwork.json --output-dir outputs/reference-artwork --output-format json
uv run python -m dataset_generator_m1 reference project --manifest examples/reference/projection.json --output-dir outputs/reference-projection --output-format json
```

The artwork example is **synthetic artwork, not camera evidence**. Audit manifests declare domain/role,
`image_root`, unique image IDs, paths, optional capture/session/location fields, target COCO boxes and
condition/physical-measurement provenance. Audit reports target size in pixels/relative area, clipping,
luma/color and Laplacian-variance proxies. These cannot identify optical blur, sensor-noise parameters
or deployment augmentation probabilities. Hash duplicates do not establish session independence.

Projection inputs explicitly supply a finite 3x3 `camera_matrix`, rigid 4x4 `world_to_camera`, positive
`target_size_m`, `image_size`, and optional four observed corners. Camera axes are OpenCV x-right,
y-down, z-forward. The centered target lies on world Z=0; corner order is (-x,-y),(+x,-y),(+x,+y),(-x,+y).
The image must be in undistorted pinhole coordinates. The fixture's two-meter target is a configured
mathematical test, not a measurement of the supplied artwork. No parameters are fitted.

Future calibration needs representative permitted real captures, verified target metric dimensions,
camera intrinsics/geometry, deployment degradation distributions and session/location identities.
Keep development references separate from the final real holdout. Actual real-image predictions and
training provenance are needed before evaluating transfer (#59/#61).

## Reproduce the plumbing check

```sh
uv run python scripts/smoke_analysis.py --pool outputs/pool --output-dir outputs/analysis-smoke
```

This deliberately constructs perfect predictions from synthetic ground truth. AP≈1 validates adapters
and scoring only; it is never a trained-model result. Keep raw outputs ignored; promote only compact
reviewed evidence. See REALISM_ROUND_ONE.md for current boundaries and later BlenderProc use (#64).
