# Quick Colab GPU screen

The current camera/ground scene was tested at 32 samples on an L4 standard shape (12 CPUs, approximately 53 GiB system RAM) and a T4 standard shape (2 CPUs, approximately 12.7 GiB). Native GPU OIDN and guarded initialization were used with identical input scenes. Each result is **one** clean measured command containing four accepted images after a separate warmup; startup, annotations, retries, rendering and writes are included in the measured command. This is a short screen, not a stable hardware-class benchmark. All tested matching full/visible mask hashes agree. The initial screen was excluded because progress-file transfer overlapped timing.

| GPU | Resolution | Workers × threads | Accepted images/s | Estimated images/CU | Peak process-tree RSS GiB | Sampled GPU memory MiB |
|---|---:|---:|---:|---:|---:|---:|
| L4 | 640² | 1 × 2 | 0.470 | 1098 | 1.38 | 1598 |
| L4 | 640² | 2 × 1 | 0.573 | 1340 | 2.58 | 3200 |
| L4 | 1280² | 1 × 2 | 0.215 | 504 | 1.48 | 2116 |
| L4 | 640² | 4 × 1 | 0.634 | 1483 | 4.78 | 5968 |
| L4 | 1280² | 2 × 1 | 0.287 | 670 | 2.91 | 4216 |
| T4 | 640² | 1 × 2 | 0.372 | 1251 | 1.31 | 1037 |
| T4 | 640² | 2 × 1 | 0.316 | 1062 | 2.33 | 1973 |
| T4 | 1280² | 1 × 2 | 0.151 | 509 | 1.29 | 1545 |

Colab reported 1.54 CU/hour for L4 alone and 2.61 CU/hour for both sessions; 1.07 CU/hour is the inferred incremental T4 rate. Images/CU above extrapolates measured-command throughput at those rates and excludes setup, capability probes, warmups, export and transfer. Both sessions together used approximately 0.28 CU according to the rounded starting/ending balance, including initial setup and discarded exploratory runs. Both were stopped and usage returned to zero.

The CLI reported a single L4 machine shape: `--high-mem` was ignored. The actual standard L4 allocation already had 12 CPUs and about 53 GiB RAM; no smaller L4 or separate higher-memory L4 was measured. Local CPU has no new comparable multi-image measurement; the earlier single-image CPU smoke is not a GPU comparison. Colab availability, hardware and prices may vary.

## Use the saved experimental policies

The policies in `experiments/blenderproc/execution/quick-screen-profiles.json` are explicit choices, not automatic hardware defaults. Generate a normal pilot configuration from a base whose asset paths are valid:

```sh
uv run python scripts/select_blender_screen_profile.py --config configs/local/pilot.json --profile colab-l4-screen --resolution 640 640 --output configs/local/pilot-l4-640.json
uv run python scripts/select_blender_screen_profile.py --config configs/local/pilot.json --profile colab-t4-screen --resolution 1280 1280 --output configs/local/pilot-t4-1280.json
uv run python scripts/select_blender_screen_profile.py --config configs/local/pilot.json --profile local-cpu --output configs/local/pilot-cpu.json
```

The L4 policy selects four workers × one thread at up to 640² and two × one for larger images; the T4 screen policy selects one × two. These are unconfirmed extrapolations away from the two measured resolutions, not general hardware defaults. Existing automatic policies are unchanged. The selector and configuration data are included in newly built portable bundles. Neither GPU result establishes real-image fidelity, detector accuracy or final wall/motion/distortion qualification.

The ignored raw archives under `outputs/experiments/realism-camera-round/gpu-screen` contain exact driver code, per-cell configurations, images, mask files, logs and resource observations; their SHA-256 values and compact metrics are in `compact.json`. Re-running the retained driver requires a prepared portable workspace and distinct output directory; it assumes the specific case list used here. For a broader comparison, use a saved-matrix study and repeat in alternating order.
