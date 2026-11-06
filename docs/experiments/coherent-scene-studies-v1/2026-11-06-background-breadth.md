# Background breadth: 2026-11-06

The local 2D catalog held 82 paths in ten categories, representing 81 distinct
SHA-256 contents; dirt_ground/Ground068.jpg and rocky_ground/Ground068.jpg were
identical. The normal catalog was not restricted for this study. No new assets
were acquired. The 3D candidate instead used three ground material manifests and
two HDR environments; the present screen is 2D only.

A fresh seed 20261106 yielded 82 paired 640×640 slots per family for landing-pad,
landing and manometro. Each pair compared coherent-varied and coherent-balanced,
using the normal recipe weights, one worker and one native thread. All 246 pairs
passed pool inspection and had identical geometry, annotations and mask signatures;
background recipes, selected source hashes and sampled background parameters also
matched within pairs. Candidate scenes used 72 distinct source paths (71 distinct
content hashes); 57 distinct paths occurred as the first source. Palette, mask and
displacement inputs may affect a composition without remaining visually identifiable.
The natural run selected direct/palette/multiband/displaced 97/65/65/19 times.

Two follow-ups generated 25 forced-direct landing-pad examples for the paths absent
from the natural first-source selections. Across natural and forced cases, all 82
paths occurred as first/direct inputs. The forced cases are deliberately selected
and are not evidence of deployment or natural sampling frequencies. Reused assets,
related seeds and paired scenes limit independence; no detector performance or
real-image calibration was measured. The stronger appearance choices remain opt-in.

The wide screen exposed varied contrast and clutter across grass, asphalt, tiles,
wood, chipboard and gravel. Some gravel and tile features look large compared with
the target; added material count alone cannot establish physical scale or deployment
relevance. Review per-scene shadows, blur and readability as well as the source.

The normal candidate run sampled 3/7/15/off motion kernels in counts 33/14/6/29
for landing-pad, 32/14/6/30 for landing and 25/11/5/41 for manometro. These are
small realized draws, not calibrated distributions. Earlier synthetic evaluations
and candidate-selection limitations are recorded in the neighboring profile report.

The main monitor recorded 402,407,424 bytes peak summed process-tree RSS, 3,734,298,624
bytes minimum available host memory, 913,408 bytes system-wide swap writes and no
guard warnings. This is one local guarded screen, not a portable speed or safety
claim. Raw pools and reports remain ignored under `outputs/experiments/`; preserve
them separately from source and do not automatically delete or commit them.

## Reproduction and provenance

The checked-in driver `experiments/foreground-context/coherent-study/run.py` had
SHA-256 `6e2313977dee271abbe551e2e6ff044f442a3bb1798221f7f62ad80948a86bb4`
when the study ran; the saved one-worker policy had SHA-256
`1edf3fe226f73e6f6bbbd6653156b59b0717d14cbd77d5d5fb0a783554a06433`.
On a checkout with the same foreground/background assets and dependencies, run:

```bash
PYTHONPATH=src python experiments/foreground-context/coherent-study/run.py \
  --output-dir outputs/experiments/background-breadth-NEW \
  --families landing-pad landing manometro --treatment coherent-balanced \
  --baseline coherent-varied --samples 82 --seed 20261106 --size 640 \
  --policy experiments/foreground-context/coherent-study/one-worker-policy.json
```

The retained original forced-direct and report scripts are
`background-breadth-cover-missing.py`, `background-breadth-cover-primary.py`, and
`background-breadth-report.py` alongside that driver. Their original source hashes
are respectively `7e85b075de4d09261c4a584d016ad03ab1eda46c41b3be8cc28c68347ef0d9f1`,
`b0f88705fb4d2e65b58d944c376c29f07d864a605855d425d252d398ddf9d017`, and the
SHA-256 of the tracked report file. These are historical snapshots, with fixed output
paths for this run: adapt a copy to fresh paths or run in an isolated checkout. The
original frozen source, policy, invocation, per-image source hashes and all outputs
remain in `outputs/experiments/background-breadth-20261106*`. The gallery at
`outputs/experiments/pr89-profile-review/background-breadth-complete/` is local-only.
Changing code, dependencies or assets produces new evidence, not an exact rerun.
