# Experiment output retention

Raw runs in `outputs/experiments/` are ignored and can be large. Inspect before making any retention
choice; no cleanup is automatic. The read-only inventory reports each top-level entry's observed byte
count, files, metadata, report and evidence hints:

```bash
python3 scripts/inventory_experiments.py outputs/experiments
python3 scripts/inventory_experiments.py outputs/experiments --json
```

Use `--max-entries` and `--max-depth` to bound work per top-level item. Symlinks are not followed;
truncated or inaccessible entries report incomplete sizes. The status is a metadata-presence hint,
not a verdict about completion, quality or safe deletion. Inspect the run's own records and related
tracked report before deciding what it means.

Preserve study definitions, source/configuration and asset fingerprints, seeds, environment and
hardware details, complete measurement denominators, decision rationale and selected visual evidence.
Keep failures, aborted runs and resource guard records when they explain a verdict or limitation.
Before any manual removal, confirm whether irreplaceable source assets, provenance, reports, selected
outputs or reproducibility evidence exist elsewhere; archive what is needed and obtain the appropriate
owner's decision. Never mix raw generated outputs into tracked source by accident. Reviewed compact
artifacts belong in `docs/experiments/` with working links and clear scope.
