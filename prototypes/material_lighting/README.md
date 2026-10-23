# PROTOTYPE: material-map lighting

Question: does aligned normal/roughness lighting add enough ground appearance control to justify a
production lighting contract? Four image columns share each family's production scene plan and masks.
The TUI changes the light direction, surfaces state/cost, and explicitly writes an ignored contact sheet.

From a prepared checkout with the Ground068 bundle under outputs/materials:

```powershell
uv run python prototypes/material_lighting/cli.py
```

Add `--demo` for one recorded comparison. Pass `--material-dir` to use an existing bundle elsewhere.
This is a fixed-plane qualitative approximation. It does not model cast shadows, calibrated BRDFs,
physical camera scale, changing surface geometry, or coherent lighting on the printed pad itself.
The contact sheet is evidence for a later decision, not a new default. No prototype shell is merged.
