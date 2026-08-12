# PROTOTYPE — Segmentation Evidence

Question: does one cropped alpha archive per sample preserve overlapping full/visible instance evidence
compactly while supporting a bounded-fidelity YOLO polygon and useful visual QA?

Run from this worktree:

```powershell
uv run python prototypes/segmentation_evidence/run.py
```

The command writes a disposable report under `outputs/prototypes/segmentation-evidence/`. This shell is
throwaway and must not be merged. Only a reviewed evidence/archive interface and polygon policy may be
reimplemented in production.
