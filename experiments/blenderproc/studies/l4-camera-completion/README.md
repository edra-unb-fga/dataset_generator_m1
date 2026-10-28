# L4 camera continuation: captured study definition

These are the phase matrices, remote controller and timing driver used for the adjusted 2026-10-28
L4 continuation. The detached local supervisor adds proxy-token redaction to the captured controller. `completion-plan.json` records the hashes of its
immutable development and held-out input bundles; those bundles and asset paths remain in ignored
experiment outputs. The configured study inside each bundle chose `gpu-guarded`, six workers and two
threads. Actual workers are capped by the number of selected jobs. Adaptive memory parameters are
loaded from the bundle's `execution/adaptive-guards.json`; the resulting limits and measurements are
saved in the results, not embedded in the controller.

To rerun with the retained bundles, use a fresh output directory and unique session name. The local
input directory must contain both input archives, the development bootstrap `.run.py`, these matrices,
`completion-plan.json`, and `speed.py`. Pass this directory via `--input-dir` and this tracked folder
via `--scripts-dir` to `supervisor.py`. The controller allocates an L4, uploads inputs, invokes
`remote.py`, verifies and retrieves its final archive, and stops its named session. A local watchdog
attempts to release an abandoned session. Cleanup cannot be guaranteed after a local host failure,
network loss or revoked credentials. Do not start overlapping compression/download and timed cells.

For new inputs, build fresh portable bundles using the harness guide, put their SHA-256 values in a
new copy of `completion-plan.json`, and use fresh output and session names. Do not overwrite the saved
matrices or conflate new source/input identities with this result. Each completed camera cell is
packaged at a between-cell barrier; verify and import archives with `scripts/handoff_study_cell.py`.
A standalone combined archive is retrieved when the complete remote command ends. `speed.py` compares
ground modes using separate warmups and alternating order; its positional arguments are output root,
workspace containing `run-config.json`, BlenderProc executable and Blender installation path.

The additional `high-quality-matrix.json` and `high-quality-plan.json` record the separate 1280²,
128-sample follow-up. To use that plan, provide a copy of the matrix as `quality-matrix.json` in the
fresh input directory and use the corresponding plan as `completion-plan.json`; preserve the originals.
