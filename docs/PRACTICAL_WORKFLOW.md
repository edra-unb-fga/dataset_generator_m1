# Practical dataset workflow delivery

The product goal is a usable dataset tool with reusable internals: configure, preview, generate,
interrupt, inspect and export with explicit content, limitations and costs. The normative current
contract remains SPEC.md. This document records the approved delivery sequence; unchecked capabilities
must not be presented as implemented.

## Delivery sequence

1. Run ownership and malformed-pool inspection (#49, PR #51).
2. Complete placement, resource, calibration and source-identity evidence (#50).
3. Separate `landing-pad` family, explicit best-effort/require-count policies and shared CLI discovery.
4. Pre-generation feasibility/partition manifests and explicitly weaker background-disjoint export (#33).
5. Reviewed drone presets, reproducible colour-material acquisition and planar mapping.
6. Hardware-aware execution plans, portable benchmark bundles and individually measured optimizations (#28).

The review stack is PRs #51, #53, #54, #55, #58, then the execution-planning PR. Later branches include
earlier commits; merge/review in dependency order. Read each PR's behavioral evidence rather than
assuming an open stack has already landed on `main`. Cross-computer instructions: EXECUTION.md and
the handoff section in the PR descriptions.

Keep each delivery in a bounded PR with its required behavioral evidence and ci:full. Historical
issues and studies remain intact. A closed issue is not evidence that every acceptance guarantee has
been verified; repairs link back to the delivery they complete.

## Decisions

- One family describes one annotation task. `landing-pad` labels the whole flat rectangular pad.
  Landing/manometro remain maintained and share rendering/annotation primitives with the new task.
- Multi-pad composers are starting configurations, not validated real-world count distributions.
- Best effort preserves existing behavior. Require count rejects a candidate that cannot meet its
  sampled count, within explicit retry limits; it never silently falls back.
- Strict asset-disjoint prevents shared source content. Background-disjoint permits shared foreground
  artwork and explicitly discloses that choice. Material maps and known derivatives share identity.
- Portable fresh runs preserve comparable scene/content intent and record execution/environment
  differences. Cross-machine resume and cross-version pixel equality are not promised.
- Users retain all effects. Hardware settings cannot silently reduce dimensions, masks or appearance.
- Runtime priors, observations and configured versus measured conditions have distinct meanings.

## Study and promotion gates

Use forced diagnostic fixtures plus naturally sampled runs. Two warmups and twenty measured fixtures
are an initial screen; report effect activation counts, uncertainty and gaps. Appearance-only pairs
hold scene intent fixed. Material studies disclose changed content. Compare end-to-end accepted
throughput, retries, exclusive stage costs, encoding/writing, QA and peak memory.

Drone preset review considers scale, perspective, coherent lighting, surface plausibility, camera
degradation, visibility and annotation validity. Real images may inform that review. Visual plausibility
does not demonstrate detector accuracy. Existing defaults change only through a reviewed decision.

Colour-texture acquisition/mapping precedes material lighting. Retain the normal/roughness lighting
prototype in its own worktree/branch; merge accepted production logic only after reviewing the result.
Cache, native-thread and scheduling changes are measured independently before combinations are promoted.

## Remaining roadmap

- #29: placement fulfillment after complete evidence, preserving explicit policy semantics.
- #27: reviewed visual warning calibration, distinct from geometry/annotation failures.
- #33: source feasibility before rendering and verified partition guarantees at export.
- #28: portable benchmark protocol now; stable hardware-class conclusions require additional machines.
- #31: accepted typed nesting remains later and is not required for ordinary flat-pad generation.

Future model evaluation consumes external predictions and dataset manifests, keeps real evaluation
separate from synthetic regressions, and analyzes class/scale/perspective/visibility/material/camera
slices. Preserve sample/evidence links and provide scripts plus agent guidance, without adding a
training dependency to the generator. Shared-memory/background caching, COCO/RLE, physical calibration,
non-planar mats, GPU/distributed execution and a GUI remain separate later decisions.
