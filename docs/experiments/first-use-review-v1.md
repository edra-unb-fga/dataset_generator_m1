# First-use workflow review, 2026-10-28

This bounded review used fresh Luna agents given tasks rather than command recipes. They ran against
merged `main` on the local Linux machine, with pool and export outputs under `/tmp`. This is an agent
walkthrough, not a substitute for observing new human users. Existing assets and an existing virtual
environment were available; dependency installation, a clean machine and Blender rendering were not tested.

## Results

- A one-image landing-pad pool was configured, validated, generated and inspected; four pad instances
  had mask evidence, and detection and visible-mask segmentation exports were produced. Independent
  inspection found four polygons, minimum reported polygon/mask IoU 0.995, and no fidelity warnings.
  One sample cannot establish distribution quality. The agent inspected an overlay, not a realism score.
- A separate 20-image landing run was paused, continued and stopped at 13 images, then resumed with the
  same inputs to 20/20. JSON run status exposed the desired and actual states. An attempted inspection
  while the coordinator was active was invalid; the precise cause was not isolated.
- CPU Blender study preparation succeeded with existing PBR/HDR assets and a prior reference pool,
  selecting one CPU worker and no GPU guard. No Blender process was launched. A subsequent one-command
  CPU setup also succeeded using the new landing-pad pool and existing assets.

## Friction and follow-up

- In a narrow terminal, the catalog truncated profile IDs; the human output now prints copyable IDs.
- Human `run status` hid the actual control state; it now shows effective, actual and requested states.
  Human pool inspection now reports findings instead of only saying that generation failed.
- The README now explains a single-split export for tiny smoke tests, `data.yaml`, and the separate local
  performance observation. The Blender guide includes CPU preparation and explicit prerequisites.
- The sandbox could not write the default `uv` cache and could not download a missing dependency;
  an existing `.venv` was usable. This is an environment-specific observation, not proof that ordinary
  installation is broken. Re-test installation on a fresh, network-enabled machine.
- A fresh agent completed an interactive `start` journey for a two-image pad pool and detection export.
  It found a crash on exit, a silent gallery action and empty validation/test splits in the export. The
  CLI now exits normally, shows the gallery path and displays split counts and empty-split warnings.
- Remaining UX research: first-time asset acquisition and actual CPU/GPU rendering, failure diagnostics
  for active inspection, and real human walkthroughs.
