# Dataset Generator M1 Agent Notes

## Mission

Build the new synthetic data generator from `NEW ARCHITECTURE.md` and the docs in `docs/`. The prototype/reference folders may be deleted, so rely on the self-contained docs rather than old code paths. The new application must follow the staged pipeline and YAML schema, especially the shared perspective transform between foreground and background.

## Source Of Truth

- Primary spec: `NEW ARCHITECTURE.md`
- Planning docs: `docs/IMPLEMENTATION_PLAN.md`
- Reference notes: `docs/REFERENCE_NOTES.md`
- Config schema: `docs/CONFIG_SCHEMA.md`
- Example configs: `examples/configs/`

## Implementation Principles

- Prefer a fresh package under `src/dataset_generator_m1/`.
- Keep stages explicit: config loading, asset discovery, background generation, foreground generation, shared perspective, assembly, annotation, final filters, output writing.
- Use Albumentations for image-only filters. Implement affine, perspective, crop, placement, and YOLO bbox math in local geometry utilities with tests.
- Preserve RGBA alpha for foreground filters. Apply color/noise filters to RGB while keeping the alpha mask stable unless a specific transform intentionally changes geometry.
- Treat perspective parameters as per-image sampled state created by the orchestrator and passed into both background and foreground workers.
- Do not copy large chunks from old code. Extract behavior: alpha-visible bbox, non-overlap placement, rotation behavior, CLI/config override shape.

## Expected CLI Shape

```powershell
python -m dataset_generator_m1 generate --dataset-type landing --config configs/landing.yaml --num-images 50 --output-dir outputs/landing-smoke --debug 10
```

CLI overrides config only for declared command-line parameters. Unknown config keys should fail validation with a useful message.

## Testing Checklist

- Config loading and CLI override precedence.
- Asset discovery for `manometro` and `landing`.
- Square rotation preserves the full rotated foreground canvas.
- Circle rotation crops back to a tight visible alpha/object bbox.
- Tiled background can legally provide the selected centered crop.
- Shared perspective parameters are identical for paired foreground/background generation.
- YOLO annotations match alpha-visible bboxes after placement and crop.
- Debug images draw bbox overlays and include stage samples.
