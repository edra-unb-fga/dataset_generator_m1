# Isolated surface context prototypes

Two experimental scene modifications reuse the exact prepared pilot renderer. `relief` places two shallow elliptical mounds outside every pad's projected ground footprint. `imported` places a Poly Haven rock and group of dry branches beside that footprint. Both participate in beauty and visible-mask passes; the full-mask pass hides all non-pad meshes and are context, never pad classes. Placement is deterministic for each attempted base scene and the group bottoms touch z=0. Intersections with pad bounding rectangles abort. This conservative placement may put context outside the camera; `prototype-context/<job>/attempt-<n>.json` records bounds, transforms, triangles, bottom height, pad intersection and camera-space center so that outcome remains visible in evidence. A bounding box contact is not a guarantee of actual mesh-ground contact. The `relief` spheres share the pilot ground material; they are separate geometry, not displacement of the flat support.

Prepare assets and the original study on the execution host first. Use the prototype checkout's adapter while the main source package is importable. Paths in the manifest are absolute, so make the manifest on the execution host after copying the self-contained GLBs and their provenance manifests. Prepare an individual manifest and new destination for each hypothesis; the derived study intentionally has no old results or run records.

```python
import importlib.util
from pathlib import Path
p = Path('/path/to/prototype/experiments/prototypes/surface-context')
spec = importlib.util.spec_from_file_location('surface_context_adapter', p/'adapter.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
renderer = '/path/to/main-source/experiments/blenderproc/render.py'
jobs = ['000-treatment-fast']  # select 1–4 existing base study IDs
# Execute once for each kind, with fresh manifest and output names:
a.write_manifest('/path/relief-manifest.json', kind='relief', renderer=renderer, job_ids=jobs)
a.prepare_prototype('/path/base-study', '/path/relief-study', '/path/relief-manifest.json')
a.write_manifest('/path/imported-manifest.json', kind='imported', renderer=renderer, job_ids=jobs,
                 provenance_manifests=['/path/rock_07/manifest.json', '/path/dry_branches_medium_01/manifest.json'])
a.prepare_prototype('/path/base-study', '/path/imported-study', '/path/imported-manifest.json')
# Immediately before every run, verify source, inputs, entry, asset hashes and provenance.
s = a.load_study('/path/imported-study')
a.verify_prototype(s, '/path/imported-manifest.json', renderer)
```

Run the prototype entry with the existing resource monitor, coordinator lease and shared budget ledger; never call the standard `run_study`, which selects the base renderer. Example command array (append the selected IDs):

```python
command = [blenderproc, 'run', str(p/'render_context.py'),
           '--renderer', renderer, '--study', '/path/imported-study/study.json',
           '--execution', '/path/imported-study/execution.json',
           '--prototype-manifest', '/path/imported-manifest.json', '--jobs', *jobs,
           '--blender-install-path', blender_install_path, '--temp-dir', '/path/worker-temp']
```

The caller owns the coordinator lease, verification, completion checks, execution monitoring, budget accounting, and standard export/report operations. The entry verifies the renderer, derived study, execution fingerprint, manifest, own source, asset files and provenance again inside Blender. Host `verify_prototype` invokes the main `validate_inputs`; the original inputs and sources therefore remain pinned. It is essential to call host verification on every launch or resume. No network or GPU work is performed by preparation.

No render or Blender import has yet validated this experimental code. In particular, verify the pinned Blender GLB importer and group transforms in the bounded prototype run before treating the geometry or evidence as valid.
