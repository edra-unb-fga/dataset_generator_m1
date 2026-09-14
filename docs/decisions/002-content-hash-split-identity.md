# Decision 002: Content hashes define strict asset-disjoint identity

Strict asset-disjoint planning identifies foreground and background sources by their content hashes.
Logical paths remain lineage/provenance, not isolation keys.

This prevents renamed or copied byte-identical assets from crossing a strict split. Pools without the
required hashes remain inspectable and detection-exportable, but strict asset-disjoint analysis/export
refuses them with migration guidance rather than claiming a guarantee it cannot establish.
