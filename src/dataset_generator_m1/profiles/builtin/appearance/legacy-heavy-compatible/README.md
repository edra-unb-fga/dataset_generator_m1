# Legacy heavy compatible

Restores the supported appearance behavior recovered from commit `a3dec1f`, including the original depth-dependent `AtmosphericFog` settings through the local native implementation.

This is intentionally heavy and requires an explicit warning receipt. It is useful for compatibility studies and visually aggressive training sets, but it is not the normal default. The historical `augmentation-heavy-v1` report remains unchanged: at that time it used a disclosed `RandomFog` approximation because Albumentations 2.0.8 did not expose `AtmosphericFog`.

The largest known drivers are foreground count, megapixels, plasma sizes, and effect activation. New studies must not compare its native fog timings directly with the archived approximation without labeling the implementation difference.
