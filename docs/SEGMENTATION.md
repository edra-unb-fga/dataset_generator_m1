# Instance segmentation

Pool schema v2 retains exact per-instance alpha coverage, so detection and segmentation exports can be
created from the same accepted samples without rerendering. Exact cropped uint8 masks are canonical;
polygons are measured, lossy export representations.

## Semantics

- `full`: the projected silhouette clipped to the output frame before later objects occlude it.
- `visible`: the coverage still attributable to the object after later objects are composited.
- `family`: use the family annotation policy (`visible` for landing and manometro).

The binary policy is currently `alpha > 8`, matching detection boxes. Landing follows the alpha-defined
circular base; manometro deliberately retains the complete transformed square. Current families do not
overlap objects, so their full and visible masks normally coincide.

## Export

```powershell
# Detection remains the default.
uv run python -m dataset_generator_m1 export `
  --pool outputs/my-pool `
  --format yolo `
  --output-dir outputs/my-detection-export

# Instance segmentation uses the family policy unless explicitly overridden.
uv run python -m dataset_generator_m1 export `
  --pool outputs/my-pool `
  --format yolo `
  --task segmentation `
  --mask-semantics family `
  --output-dir outputs/my-segmentation-export
```

The exporter validates every pool and archive before creating the destination. Each mask is converted to
one normalized YOLO polygon with targets of at least `0.995` rasterized IoU and at most `1%` absolute area
error. Holes and disconnected components cannot be represented exactly by one YOLO polygon: export
continues deterministically, records per-instance findings in `export.json`, and returns
`complete_with_warnings`. The pool mask remains lossless and unchanged.

Pool-v1 remains inspectable and detection-exportable but cannot export segmentation or resume as v2.
Nested placement and COCO/RLE are separately planned because they change scene semantics and topology
rather than the evidence-storage foundation.
