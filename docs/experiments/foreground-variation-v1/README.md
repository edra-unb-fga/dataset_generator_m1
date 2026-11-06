# Foreground variation and capture-effects screen

These paired 640×640 local 2D screens reuse the coherent-varied scene lighting and the same seed, asset catalog, placements and geometry per family. Treatments are forced diagnostics for visual comparison, not proposed frequencies. Same asset catalog and synthetic images are not independent real-world validation. No defaults changed.

## Foregrounds

Eight matched scenes for each of landing-pad, landing and manometro compare four treatments: no foreground wear or grain; forced existing subtle `SurfaceWear` (fade .03, dirt .06, scratches .04, six marks); stronger `SurfaceWear` (fade .08, dirt .22, scratches .16, twelve marks); or forced foreground Gaussian grain (standard deviation .02–.04). The grain is unstructured Gaussian noise, not a material texture. Existing scene lighting and final-stage effects remain sampled identically across treatments. All 96 samples were accepted; inspected pools were valid and geometry, annotation and full/visible mask signatures matched per family. Guards observed peak process-tree RSS 358,248,448 bytes, minimum available 7,493,873,664 bytes, and 2,560,000 bytes system-wide swap-out.

The stronger existing wear clearly adds marks but can expose repeated oval dirt shapes, particularly on light landing targets; fine grain can largely disappear after foreground resizing. A few selected crops cannot establish prevalence, detector benefit or realistic material response. Full scenes and largest-visible-target crops are included; crops retain context and are not source-resolution renders.

## Camera capture

Five matched scenes per family compare a clean final capture stage against forced whole-image Gaussian noise (standard deviation .02–.04), forced 3–5-pixel motion blur, and forced JPEG compression at quality 45–65. Capture effects are applied separately, not together. Normal foreground effects and scene illumination remain active; the clean capture still goes through the generator's normal image output encoding. Consequently JPEG compression may be encoded again at output and should be interpreted as a pipeline example, not a single-codec calibration. All 60 samples were accepted; pool inspection and per-family geometry/annotation/mask signatures matched. Peak process-tree RSS 352,083,968 bytes, minimum available 7,383,322,624 bytes, and 2,588,672 bytes system-wide swap-out were observed.

On selected crops, noise is visibly grainy at the tested stronger setting, motion blur can erase small gauge details, and JPEG softening/blocking varies with content. These examples support a visual comparison, not measured robustness or physically calibrated camera noise. [Camera-effect research](camera-effects-research.md) discusses evidence, stronger limitations and possible use with both engines.

## Reproduction and evidence

Each ignored study root retains its exact driver source, invocation, seed, policy, source hashes, effect traces, output pools and resource monitoring. Paths are `outputs/experiments/foreground-variation-paired-20261105` and `outputs/experiments/camera-capture-paired-20261105`. These retained local artifacts are not supplied by a fresh checkout; the copied driver records the local workspace path and must be adapted for reproduction elsewhere. The locally served gallery contains the 156 images plus 156 largest-target crops. See `docs/EXPERIMENT_RETENTION.md` before removing or committing output pools.

## Post-render 3D proof of concept

The existing 2D final-stage pipeline was also applied offline to four previously verified BlenderProc RGB renders (indices 000, 007, 010 and 015), using clean, forced Gaussian noise, forced motion blur and forced JPEG treatments at the same ranges as the 2D capture screen. These 16 PNG outputs demonstrate that the RGB-only transform code can operate on rendered 3D images; they are not new BlenderProc renders, a supported integrated pipeline, a model benchmark or a test of physically simulated optics. Original 3D mask and annotation files were not modified. The gallery records input/output SHA-256, original 3D metadata and effect traces; original 3D assets and study outputs remain local.
