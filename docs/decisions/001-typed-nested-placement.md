# Decision 001: Family-declared typed nested placement

Status: accepted for future implementation in [#31](https://github.com/edra-unb-fga/dataset_generator_m1/issues/31).
No production nested behavior exists yet.

## Context

Pool-v2 can retain overlapping full and visible masks, but a single containment model cannot represent
both a marking physically attached to a parent and an independently placed object inside a projected
container. Prototype [#24](https://github.com/edra-unb-fga/dataset_generator_m1/issues/24) compared
parent-local attachment, projected containment, and a typed combination.

## Decision

Families declare allowed parent/child compatibility and one of two relationship types:

- `attached-local`: compose the child-local transform with the parent transform. Parent movement and
  rotation move the child exactly.
- `projected-contained`: independently sample the child in output space and require its coverage to
  satisfy a family-declared containment threshold inside the parent's projected silhouette.

The production model is called `typed-mixed` because one family may declare different relationship
types for different parent/child roles. Hierarchy (`parent_id`), stable instance identity,
relationship type, and deterministic compositing order remain separate evidence. Full masks describe
coverage before later-object occlusion; visible masks follow final compositing.

Landing and manometro declare no nested compatibility and must remain unchanged flat controls.

## Consequences

- A family cannot gain nesting implicitly.
- Incompatible relationships and containment failures produce bounded diagnostics.
- Tests require a synthetic fixture family rather than mutating maintained family semantics.
- A general scene graph, COCO/RLE export, training integration, and nested landing/manometro behavior
  remain out of scope.

## Primary source

Retained branch `codex/prototype-nested-placement`, commit `46c0e96`.
