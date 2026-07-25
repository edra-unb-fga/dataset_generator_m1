# Dataset Generator M1 Domain Context

This file defines the project language. It intentionally describes the domain, not the implementation.

- **Family**: one coherent annotation problem with an ordered class catalog, asset-mapping rules, and geometric policies. A run has exactly one family.
- **Generation profile**: the strict, versioned experiment contract that selects a family and defines run, assets, output, sampling, scene, background synthesis, appearance, telemetry, and reporting behavior.
- **Asset catalog**: the validated, fingerprinted inventory of decodable source images, mappings, groups, metadata, and sampling weights available to a run.
- **Background recipe**: a versioned, typed, acyclic graph that combines one or more catalog backgrounds into one RGB scene canvas.
- **Scene plan**: deterministic sampled intent for a slot and candidate attempt: asset choices, normalized random draws, placements, camera window, recipe, and one global homography.
- **Candidate**: one attempt to realize a slot. It either becomes an accepted sample or produces a typed rejection record.
- **Sample**: an accepted rendered image with annotations, geometry evidence, source lineage, timings, and QA evidence.
- **Generation pool**: a resumable, auditable collection of compatible samples and rejections. It is not yet a train/validation/test dataset.
- **Variant**: a named, schema-validated overlay used to compare experimental scene or appearance settings while preserving shared choices and random quantiles.
- **Exported dataset**: one or more compatible pools remapped and split into a training format such as YOLO.

## Invariants

1. Foreground and background inhabit one coplanar scene and use the same scene-to-output homography.
2. Detection boxes are derived from final transformed visible instance masks.
3. A foreground maps to exactly one declared class; class order is explicit and stable.
4. Random streams are derived from `(run_seed, slot, candidate_attempt, stream_name)`. Appearance, telemetry, display mode, and worker count cannot alter scene plans or annotations.
5. Exact Albumentations pixels are not a reproducibility promise. Scene identity, geometry, annotations, lineage, and ordered records are.
6. Empty samples are intentional negatives. Accidental all-rejected candidates do not silently become negatives.
7. Workers render candidates and return compact results. Only the coordinator writes pool state or terminal output.
