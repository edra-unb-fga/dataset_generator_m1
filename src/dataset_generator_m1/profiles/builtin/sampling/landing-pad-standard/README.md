# Editable multi-pad starter

Requests two to six pads at relative widths 0.12–0.25. These deliberately modest starting values
are uncalibrated, not a validated count distribution. Inspect requested versus accepted counts.
`count_policy: best-effort` keeps surviving instances; `require-count` rejects incomplete candidates
within the configured candidate limit. Neither policy guarantees dataset-wide class quotas.
