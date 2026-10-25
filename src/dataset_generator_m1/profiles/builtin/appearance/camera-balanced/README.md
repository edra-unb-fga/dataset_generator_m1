# Camera balanced

Experimental camera-minimal treatment with restrained blackbody temperature variation and sparse,
low-amplitude sensor noise. Shared stable effect IDs preserve the common effects' random streams
when comparing the two candidates. Every effect operates on the final composed image.

Select with `appearance: {preset: builtin:appearance/camera-balanced}`. It trades greater camera
variation for additional noise/temperature cost; benchmark rather than assuming it is faster than
other profiles. It is not calibrated physical illumination or sensor noise, adds no contact shadows,
and makes no training-quality claim. Existing defaults are unchanged.
Evidence and limitations: `docs/experiments/profile-tradeoffs-v1/README.md`.
