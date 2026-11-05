# Controlled experiments

Start with the [study index](experiments/README.md) to find a question, its evidence and limitations.
The [historical narrative](EXPERIMENTS_HISTORY.md) preserves the original chronological detail and
reproduction commands. [Retention guidance](EXPERIMENT_RETENTION.md) explains how to inspect and
preserve local output without automatically deleting it.

Studies isolate decisions using paired inputs from the production pipeline or an explicitly separate
optional harness. Interpret results within their measured environment: use render-only cost for
appearance attribution, production cost for synthesis/encode/write, and attempt denominators for
placement rates. Fewer than 20 measured fixtures warrant caution; cross-machine thresholds require
reviewed hardware-class baselines. Keep raw pools under ignored `outputs/experiments/`; promote only
reviewed definitions, compact measurements, fingerprints and selected visual evidence.

For the augmentation or placement CLI commands and their interpretation, see the historical narrative.
Appearance-only treatments must preserve alpha and annotations; occlusion intentionally changes visible
masks. Do not infer real-image performance or detector transfer from synthetic appearance alone.

For image-first review, `scripts/build_scene_review_gallery.py` builds a portable HTML gallery
beside a JSON manifest. It filters by engine, family and condition, shows per-image metadata and
provides an enlarged viewer with keyboard navigation and a full-screen button. The companion
`collect_2d_review_gallery.py` and `collect_3d_review_gallery.py` collect committed study images;
they do not fabricate missing results or turn a partial study into a successful one. Keep the
manifest, its profile files and image directory together when moving a gallery.
