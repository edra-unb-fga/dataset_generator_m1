# RandomFog heavy

Preserves Albumentations' patch-based `RandomFog` as a first-class, materially different visual treatment. It is not an approximation of depth-dependent atmospheric scattering.

The reviewed local study found this effect to dominate slow samples, so preflight requires an explicit warning receipt. Cost varies strongly with image size and sampled fog density. Use it when patch-like occluding fog is relevant, not merely as a generic haze control.
