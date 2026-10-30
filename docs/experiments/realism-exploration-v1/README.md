# Exploratory realism screen — 2026-10-29

**Status: historical exploratory evidence.** These synthetic screens used temporary study-only renderer
patches and sentinel mappings; they are not examples of current configuration syntax, calibrated
conditions, production defaults or detector evaluation. The source was the ignored local bundle
`outputs/experiments/realism-expanded-20261029`; the sheets and compact matrices/provenance/summary
files here are selected copies. The original bundle contains the study definitions, patches, logs,
archives and further results. It has not been removed. See the JSON files beside this document for
recorded source and input fingerprints where available.

| Screen | Selected full-scene sheet | Result and limitation |
| --- | --- | --- |
| Suspended shadows | [Refined casters](shadow-refine.jpg) | Five cells, three paired scenes, 12/12 matching mask comparisons. Slats can cross targets, but these aimed fixtures are not a representative distribution; very soft shadows can disappear. |
| Indoor material and lighting | [Indoor screen](indoor.jpg) | Nine cells, three paired jobs, 24/24 matching mask comparisons. Walls and ceiling shared a material in this historical screen; added lights were not equal-illuminance matched, and some targets overexposed. |
| Haze boundary diagnosis | [Diagnostic](haze-diagnostic.jpg) | Original volume and ground lost texture even at low density; shifting its lower boundary below ground retained texture in three tested views. This identifies a likely boundary issue, not an instrumented rendering cause. |
| Corrected haze | [Strength screen](haze-corrected.jpg) | Six cells, three paired intents, 15/15 mask comparisons. Compare indoor clear with indoor medium; numerical report baseline was outdoor. Homogeneous volume is not calibrated smoke, fog or dust. The first launch timed out without image results; a serial retry supplied this sheet. |
| 2D context and wear | [2D treatments](two-d.jpg), [scratch comparison](scuff-comparison.jpg) | Six scenes; geometry and annotation signatures matched. Context can turn targets purple; scratches remain simple strokes. Neither scratch prototype was promoted. |

Exact masks establish geometric consistency, not that the target remains perceptually legible. The
3D screens reuse two sampled scenes and one close-up per treatment; the 2D examples reuse six scenes.
Current experimental presets provide explicit caster and lamp controls, but these historical studies
used temporary fixtures and cannot validate their general distributions. Real references, calibrated
materials and independent model-transfer evaluation remain open. Review [scene presets](../../SCENE_PRESETS.md)
and the [study index](../README.md) for current navigation.
