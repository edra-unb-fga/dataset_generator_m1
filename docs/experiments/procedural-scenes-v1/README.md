# Procedural scene presets: bounded visual screen

[View the image-first review](index.html), or inspect the [contact sheet](contact.jpg), [indoor scene 003 at native size](indoor-003.png), and [outdoor scene 002 at native size](outdoor-002.png).

A single L4 run rendered four ordinary scenes for each of `open`, `outdoor`, and `indoor`: 12 of 12 completed at 640 × 640, 32 samples, with seed 20261109 and the same four reference-pool scene indices. The study uses actual preset preparation and renderer code, without diagnostic fixtures or study-only renderer patches. Its input bundle SHA-256 is `a7131f04abd6b36a829c2ba48939eea9b5fb576987e960cc8ddfb906d0ee90ea`; its verified result archive SHA-256 is `46164cc1bc3e984d493349cb8f67ea704e8eda9bda5835aec29f4c4a7c4c8b68`. The remote work took 152.6 seconds; retrieval passed checksum and size verification and the supervisor confirmed runtime shutdown. Adaptive machine-relative guards and their measurements are in the ignored raw output.

The indoor samples contain strong bright pools, especially scene 003, where the center pad is visibly washed out. Scene 002 has a broad bright region. Ground texture repetition is apparent in scenes 1 and 3. The sampled top-down open and outdoor scenes are visually similar at this framing, so these four examples do not demonstrate visible room or wall diversity. In scene 002, a small black square appears at the right edge; its origin was not isolated. These are observations, not measurements of realism. Candidate refinements include reviewing lamp power, size, and placement distributions with real indoor references, plus material scale and texture diversity; do not treat these as calibrated recommended settings.

The sealed bundle predates subsequent changes: indoor emitters are now fitted by their full extents or omitted when too large; indoor casters crossing room boundaries are omitted; and procedural `scene_offset` now affects sequence and camera seeds. This run used offset zero. The boundary changes can alter indoor images, so the retained indoor images are **not renders of the final source**. Open/outdoor scenes are unaffected by these particular changes at offset zero, but were still generated from the earlier source identity. No matched high-quality reference, real-image comparison, detector evaluation, or statistical qualification was performed. The scene count is too small to justify claims about distribution coverage or photographic realism.

Raw input, provenance, logs and full-resolution images are retained under ignored `outputs/experiments/procedural-scenes-20261029/followup-run`. Reproduction uses the controller in `experiments/blenderproc/studies/procedural-scenes/`; supply a freshly built source bundle and licensed assets. The preceding exploratory bundle and run remain separately identified in the same ignored output root.

## Final-renderer local verification

Two additional ordinary indoor scenes were rendered on the final source using the existing local Blender 4.2.1 and BlenderProc installation, CPU, 640 × 640, 32 samples and seed 20261109. The [offset-zero image](final-indoor-000.png) and [offset-three image](final-indoor-003.png) both completed and were accepted. One CPU worker used a 2 GiB available-memory floor, a measured 2.61 GiB process-tree RSS limit and a 16 MiB swap-out guard. Their respective render commands took 33.4 and 32.6 seconds; this is a bounded functional check, not a throughput benchmark. Raw records and guard basis are retained under ignored `outputs/experiments/procedural-scenes-20261029/local-final`.

Both show broad bright pools; the offset-three image still visibly washes out the central target. Each recorded two actual lamp locations. These samples exercise the final indoor render path, but they do not establish that all boundary omission cases were exercised or qualify the preset distribution. The earlier contact sheet remains identified with its pre-final source.

[Local verification metadata](local-verification.json) retains image hashes, source fingerprints,
renderer settings and resolved environment evidence. After these renders, preparation was improved
to accept explicit room settings without a redundant environment mix, and preset listing became more
compact. Those interface changes have deterministic coverage; the renderer and sampler used for the
local images are unchanged. Keep the recorded source identities when reproducing the exact studies.
