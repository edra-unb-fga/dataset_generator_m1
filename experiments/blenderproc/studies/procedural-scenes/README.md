# Procedural scene preset validation

This bounded qualitative screen prepares four ordinary 640 × 640, 32-sample scenes for each of `open`, `outdoor`, and `indoor`, with a fixed seed and one ordinary treatment. It exercises the actual preset CLI and bundled renderer, without diagnostic fixtures or temporary renderer patches. It is a small synthetic sample, not a calibrated realism or detector-performance study.

Build a fresh portable input bundle from a config with explicit reference pool and licensed assets,
four scenes and one treatment named `base`. Copy the current `generate_scene_presets.py` into the input
directory. Write `spec.json` with `bundle_sha256`, `bootstrap_sha256` (the `.run.py` file), `cli_sha256`
and `total_seconds` (positive, at most 750). The source archive seals the renderer and preset
implementation; the separately uploaded CLI must match that source revision.

Run `supervisor.py --input-dir INPUT --scripts-dir THIS_DIRECTORY --output NEW_OUTPUT --session PREFIX`
in a persistent process. It validates inputs before allocation, requires a fresh output directory, adds
a unique session suffix and saves session state in that output directory. It allocates one L4, runs
`remote.py`, verifies the archive checksum and size, and stops its named session. Use the saved session
name and `colab --config NEW_OUTPUT/colab-sessions.json` when inspecting that session. Credentials still
come from the global CLI authentication setup. Failure, missing results and unconfirmed shutdown
produce nonzero exit status.

The separate watchdog attempts shutdown after the configured deadline (default 1050 seconds; at least
180 seconds longer than the remote budget). It cannot guarantee cleanup during host shutdown, network
failure, or revoked credentials. The remote derives resource limits on that machine and saves their
basis. The 750-second remote limit reserves time for retrieval and shutdown; assess actual runtime
before changing the bounded study. Controller hardening after the retained L4 runs has mocked lifecycle
coverage; it was not used to launch an additional remote validation run.

Raw bundles, logs, images, configs, and archives remain in ignored experiment outputs. Inspect complete images and selected native crops. Record visible defects and the limits of the sample rather than claiming photographic realism from the screen.
