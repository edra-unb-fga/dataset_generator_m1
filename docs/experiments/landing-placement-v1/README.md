# Landing placement diagnosis v1

This reviewed study ran the shipped `landing_minimal.yaml` composer through the normal single-worker
generation path for 200 accepted fixtures. It changed no spacing, placement-attempt, visibility, or
acceptance policy. The raw study bundle remains ignored under `outputs/experiments/`.

## Findings

- 200 accepted samples required 211 candidate attempts; 11 whole candidates were retried (5.2%).
- The requested scenes contained 1,117 object attempts. 501 objects were accepted and 616 were
  rejected, an object rejection rate of 55.1%.
- Visibility below the configured threshold accounted for 425 rejections (38.0% of all object
  attempts). Placement-attempt exhaustion accounted for 191 (17.1%).
- Rejection increased with sampled scale: 35.7% for `0.10–0.20`, 54.5% for `0.20–0.30`, and 65.2%
  for `0.30–0.40`.
- Requested object count was the clearest workload driver. One-object scenes had no object rejection
  in this fixture, while ten-object scenes rejected 72.0% of object attempts.
- The projected middle-center region rejected 7.7% of attempts. Corner regions ranged from 63.1% to
  73.1%, consistent with the reviewed overlays showing visibility/clipping pressure near frame edges.
- Rotation bands varied less consistently than scale, count, and region in this sample. No rotation
  policy change is supported by this study alone.

## Decision

Keep current behavior unchanged in the diagnostics milestone. Create a separate tuning issue focused
on requested-count fulfillment, scale-aware placement, and edge visibility. Any tuning must compare
accepted-image distributions and annotation signatures against this fixed diagnostic study.

The red rectangles in `contact-sheet.jpg` are bounded best-failure/projected rejection overlays, not
accepted annotations.
