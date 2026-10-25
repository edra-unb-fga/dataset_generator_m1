# Direct-dominant background mixture

Experimental mixture: 80% direct, 15% palette transfer, 5% multiband blending and no displacement.
These are normalized sampling weights, not quotas. Source roots, dimensions, foreground geometry,
mask persistence and background QA remain unchanged.

The explicit tradeoff is less synthesized background diversity and more source-preserving images.
This changes generated content; it is not an execution-only optimization and cannot be used as an
appearance-only paired treatment. It may suit source photographs better than aggressive mixing,
but neither visual realism nor training utility follows from the weights alone. Preserve the
standard mixture for broader synthesis coverage. No existing default is changed.

Select with `background_mixing: builtin:background_mixing/direct-dominant`.
Evidence and limitations: `docs/experiments/profile-tradeoffs-v1/README.md`.
