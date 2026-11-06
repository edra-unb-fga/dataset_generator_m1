# Cross-engine sample contract prototype

This isolated candidate is **not integrated** into either renderer, export, pool validation or resume.
The hand-authored fixtures are illustrative contract records, not real output or evidence of an adapter.
Run from the repository root using an environment with the project dev dependencies:

```bash
uv run pytest prototypes/cross_engine_contract/test_contract.py -q
```

The v1 record carries a namespaced engine, sample and source identity, image reference and optional hash,
image dimensions, optional intentional-negative and source revision, and per-instance class, optional
source identity, image-space exclusive XYXY box and full/visible evidence references. Null means unknown
or unavailable, not false or an empty mask. A class ID's meaning is scoped to its source; `0` and `1`
are not automatically equivalent across engines. A future cross-source dataset needs an explicit
versioned class mapping and conflict handling.

Observed source boundaries: 2D pool-v2 `samples.jsonl` contains slot, instance and class records plus a
`npz-cropped-alpha-v1` manifest with full/visible cropped uint8 arrays, origins, threshold and archive
hash. BlenderProc accepted `result.json` binds a study identity and job to `rgb.png` and `masks.npz`;
the latter holds full/visible binary arrays, with original retained instance indices in placement
records. Blender COCO export uses XYWH boxes and category IDs; a future adapter must explicitly
convert to XYXY and retain source class identifiers. `full[0]` in the illustrative fixture denotes an
array slice, not a literal NPZ key. Neither a binary raster nor a thresholded alpha raster is interchangeable
with original alpha coverage; no conversion is performed here.

Validation checks record types, engine-specific evidence representation, image bounds, unique instance
IDs and negative consistency. It does **not** open or hash files, decode arrays, verify subsets or boxes,
prove provenance, ensure source-wide class consistency, or establish that references are safe to open.
A real adapter must validate native archives and hashes, preserve source instance ordering and dropped
objects, establish stable IDs and record mappings/unknown values explicitly. Validate source snapshots
and version migration before producing a shared interchange format. Define coordinate frames, distinction
between full geometry and alpha contribution, and class taxonomy before downstream training consumes it.

For performance, keep references and metadata small and immutable, decode evidence lazily, stream
records, and avoid copying full-resolution masks for ordinary discovery. Benchmark adapters on paired
representative workloads with verified outputs and memory measurements across hardware; this prototype
contains no performance measurements or claim of improved throughput.

## Integration boundaries to resolve

| Area | Current boundary | Future requirement |
| --- | --- | --- |
| Configuration | The planar composer resolves a hashed family/profile contract; the pilot freezes a separate study config, assets, renderer version and execution policy. | Separate engine-neutral sample intent from engine-specific controls; version and hash both without pretending every parameter has a counterpart. |
| Scheduling | The planar coordinator owns ordered pool writes; the pilot owns and supervises Blender process trees and resumable jobs. | Define a single writer or explicit shard/merge ownership, stable sample identities and scheduling-independent random streams before shared or distributed execution. |
| Resources | The planar executor and pilot have distinct host-memory, GPU and timeout controls; Blender installs and runs in its own environment. | Publish capabilities and hardware-derived budgets separately from scene intent. Measure setup, accepted throughput and peak memory on representative hardware rather than assuming a universal worker count. |
| Failure and retry | Planar candidates have typed rejections and attempt identities; the pilot has per-job outcomes, attempts, stop guards and explicit partial export. | Map outcomes without dropping reasons, preserve attempt lineage and distinguish intentional negatives from rejected/empty work. Specify atomic commits, cancellation and restart on each engine before coordinating them. |
| Resume and provenance | Planar pool resume requires matching contracts and catalogs; the pilot binds source, assets, configuration and jobs to a study identity. | Do not resume across engines or versions without an explicit migration contract. Preserve source manifests, exact mask semantics, unknowns and an auditable origin for every sample. |

An incremental path is: strengthen the read-only native checks on varied real artifacts; define
and test explicit class maps and interchange versions; prototype one optional export adapter per
engine; then evaluate a small shared coordinator while preserving standalone operation. Only a later
review should decide whether BlenderProc becomes a selectable core backend. Separately, investigate
planar asset reuse, expensive background operations, CPU parallelism and possible GPU/distributed
execution through measured paired workloads; the current prototype provides no evidence that any
one change will improve throughput.

## Native local checks

`native_check.py` is a read-only exploratory adapter for **trusted local artifacts**. It reads the first
2D pool row or one accepted Blender scene, checks the referenced image dimensions, invokes the native
2D archive decoder or checks 3D binary dtype/shape and subset, verifies the relevant archive hash,
and validates the resulting candidate record. It limits input file size to 32 MiB; it is not a hardened
untrusted-archive reader or a full pool/study audit. The 2D source revision and source instance identity
remain unknown; the historical Blender example lacks retained-index diagnostics, so source instance
identity remains unknown there too. Its 3D `pad` class reflects the pilot's fixed category, not a
cross-engine class mapping. Decoded evidence is checked but not copied or converted.

Executed against the local 2026-10-24 `landing-base/pool` first row (640×640, one annotation) and
`blender-diagnostics-v1/scenes/000-base-fast` (512×512, four annotations). The 2D sample used the
native `same_as: full` shorthand, resolved to the same evidence key. Both candidate records validated;
these two samples do not establish broad compatibility. Outputs are ephemeral and source artifacts
remain untouched.

The checks were also run on the first row of the 2026-10-30 complete-stack landing-pad candidate
(640×640, three cropped-alpha instances, threshold 8) and on accepted Blender scene
`candidate-0/scenes/020-base-fast` (640×640, two binary instances). Both validated. The newer
3D result provided source instance identities; the 2D row did not. Its source class ID was 0,
while the pilot's pad ID was 1, illustrating why a shared class map must be explicit. The checks
remain two additional individual examples, not an exhaustive audit or an integrated adapter. To repeat
with your own artifacts:

```bash
PYTHONPATH=src uv run python prototypes/cross_engine_contract/native_check.py planar PATH_TO_POOL
PYTHONPATH=src uv run python prototypes/cross_engine_contract/native_check.py blender PATH_TO_ACCEPTED_SCENE
```
