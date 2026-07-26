# PROTOTYPE — Augmentation Study Report

Question: which image-first information hierarchy makes it easiest to connect a visible augmentation difference to its stage and processing cost?

Three structurally different layouts share the same representative study fixture and are selected with `?variant=A`, `?variant=B`, or `?variant=C`:

- **A — Contact sheet:** synchronized treatment columns, with expandable timing details per fixture.
- **B — Slow-sample navigator:** ranked samples on the left and a focused comparison workspace on the right.
- **C — Stage investigation:** one large image comparison controlled by background/foreground/final stage tabs.

Run from this worktree:

```powershell
uv run python prototypes/augmentation-report/serve.py
```

Then open <http://127.0.0.1:4175/?variant=A>. Arrow keys or the floating switcher cycle layouts.

This is throwaway UI code. The selected information hierarchy must be rewritten in the production report generator; this branch remains the primary-source record of the alternatives.
