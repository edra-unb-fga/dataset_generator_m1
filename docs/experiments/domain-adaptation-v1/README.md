# Domain adaptation and capture effects: bounded screen

The screen uses 12 previously inspected coherent 2D JPEG scenes (four each for landing-pad, landing and manometro) and four verified 640×640 BlenderProc renders. A proposed fresh 2D generation attempt stopped at the 16 MiB system-wide swap-out guard; its partial run and original policy are retained. Reusing older JPEG inputs means the compression treatment adds a second lossy stage. The 3D examples are RGB postprocessing of existing renders, not new renders or a shared production backend.

For future runs of this study only, `local-warning-policy.json` records and warns when the system-wide swap-out threshold is exceeded, while retaining the 2 GiB available-memory floor, adaptive process-tree RSS limit, and timeout. This is an explicitly selected local policy, not an automatic retry or a change to other studies' existing policies. Swap activity is system-wide and does not identify the responsible process; continued swapping, sustained memory pressure or a falling memory reserve may still warrant stopping the run. These safeguards reduce risk but cannot guarantee prevention of an out-of-memory event between samples.

Each source has 29 treatments: the untouched image; mild, strong and extreme FDA, histogram matching, color jitter, motion blur, defocus, Gaussian noise, JPEG compression and downscale/upscale; and four independently sampled combinations. At 640×640, motion kernels are 3, 7 and 15 pixels. The combination sampler uses provisional motion probabilities of 70% for pads/landing and 60% for gauges, with strong tails; four combinations per scene are far too few to establish population frequencies. Treatments are forced in isolated comparisons and do not imply recommended rates.

Three existing background photographs serve as development style references. Their logical paths and SHA-256 hashes are in `summary.json` and per-image metadata; the 2D reference is checked against each source background's exact content hash. These are not calibrated real-camera captures or an independent reference holdout, and the 3D inputs were not checked for cross-engine source-asset separation. FDA and histogram treatments pass the selected reference through Albumentations metadata. Reference choice, treatment, severity, seed, source image hash and output hash are recorded. All operations are applied after composition, without writing or changing source masks or annotations; unchanged geometric labels do not prove that a very faint or blurred target remains visually recoverable.

Visual inspection of selected cases found mild FDA can produce a substantial cast depending on reference, strong FDA can add halos or reference-like textures, and extreme FDA can make targets very faint. Strong histogram matching shifted color and reduced contrast in some examples, while extreme color jitter produced implausible but intentional stress cases. Severe motion blur impaired small details. Effects interact with the selected reference, scene and input encoding; these observations do not establish frequencies, realism, or downstream detector performance. The gallery also incorporates 48 full-image/crop cards from the prior foreground-wear comparison; it does not introduce a new structured plastic texture.

The guarded postprocess completed 16 sources × 29 variants = 464 treated images, plus 348 largest-target crops and 48 prior surface cards. The verifier opened every image and checked available image/crop SHA-256s. Recorded peak process-tree RSS was 250,335,232 bytes, minimum available memory 7,203,315,712 bytes and additional observed system swap-out 0 bytes. Results, driver snapshot, policy, reference hashes and report remain in ignored `outputs/experiments/domain-adaptation-screen-20261105`; the stopped fresh-generation attempt remains in `outputs/experiments/domain-adaptation-source-20261105`.

Reproduce the postprocess after supplying the same validated input studies and backgrounds:

```bash
PYTHONPATH=src python experiments/domain-adaptation-v1/screen.py --output-dir outputs/experiments/NEW-OUTPUT
python scripts/build_scene_review_gallery.py outputs/experiments/NEW-OUTPUT/gallery/manifest.json --output outputs/experiments/NEW-OUTPUT/gallery/index.html
```

These commands reproduce the 812 main-screen gallery cards; the 48 cards appended from the previous foreground study and the rendered study notes in the combined review are separate report additions.

The raw study manifest contains absolute local source paths and is local-only. Do not publish raw datasets or assume retained ignored outputs exist in a fresh checkout. Separate user approval remains required for each 2D family default and the 3D default.
