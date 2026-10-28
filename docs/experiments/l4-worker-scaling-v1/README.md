# Exploratory L4 worker/thread scaling

This quick single-runtime screen compares ten paired cases with 12 measured accepted images and two
warmup images per case. Values are accepted images divided by measured render-command wall time,
including worker startup, excluding probe, separate warmup, setup and download. Inputs, treatment,
32 samples and mask signatures were paired within each resolution; all 120 measured outputs were
accepted, all masks matched within resolution, and every case completed. The sample is small: only
4×1 and 6×1 at 640² were repeated, so small differences and unreplicated winners are provisional.

| Resolution | Workers × threads | Accepted images/s | Mean sampled GPU utilization | Peak summed RSS GiB | Peak GPU memory GiB |
| --- | --- | ---: | ---: | ---: | ---: |
| 640² | 2×1 | 0.925 | 16.1% | 2.80 | 3.12 |
| 640² | 4×1 | 1.200, 1.202 | 30.6%, 29.1% | 5.05, 5.16 | 6.21 |
| 640² | 6×1 | 1.235, 1.233 | 28.0%, 27.1% | 7.27, 7.39 | 8.67, 8.82 |
| 640² | 8×1 | 1.194 | 36.3% | 9.69 | 10.93 |
| 640² | 4×2 | 1.234 | 29.1% | 4.94 | 6.21 |
| 640² | 6×2 | 1.276 | 33.1% | 7.63 | 8.82 |
| 1280² | 2×1 | 0.389 | 34.1% | 2.83 | 4.13 |
| 1280² | 4×1 | 0.539 | 43.2% | 5.62 | 8.19 |

Eight workers at 640² did not improve throughput over six, despite using more memory and reporting
higher GPU utilization; this does not rule out an improvement for longer jobs or other scenes. Six
workers with two threads was fastest in this screen, about 3.4% faster than the repeated 6×1 mean,
but has no repeat and is not a reliable new default. At 1280², 4×1 was about 39% faster than 2×1;
that promising result needs repeated, alternating confirmation before changing the saved selection.
The measured utilization includes startup and annotation phases, so it cannot by itself identify the
bottleneck. System CPU averaged 19.3% across 85 five-second samples covering the study as a whole.

The L4 runtime reported 12 vCPUs, 52.96 GiB total host RAM and 22.49 GiB total VRAM. The study-derived
guards were 5.30 GiB minimum available host RAM, 41.01 GiB maximum summed process-tree RSS,
16 MiB maximum additional system swap-out and 1.80 GiB minimum free VRAM. No case triggered a guard
or observed swap-out. Sampled peaks can miss spikes; summed RSS counts shared pages repeatedly and is
not a physical-memory estimate. Every GPU render phase had telemetry, with a maximum observed
sampling gap of 1.19 seconds. The tested bundle could retain a stale GPU reading if a later query
failed; the subsequently committed monitor fails closed instead. No telemetry gap was observed here.

The displayed L4 rate was 1.54 CU/hour; displayed balance changed 159.72→159.53 CU, rounded by the
service, for allocation, staging, the entire study, retrieval and shutdown. As an approximation,
120 measured images / 0.19 CU is 632 measured images/CU for this small *whole study*, which also
includes 20 warmups, probes and setup. Render-only extrapolations such as 1.20 images/s × 3600 / 1.54
≈ 2805 images/CU exclude those overheads and should not be presented as the actual study efficiency.

The controller automatically downloaded and verified the 121,804,990-byte raw archive and stopped
the runtime; displayed usage afterwards was 0 CU/hour and zero active assignments. Archive SHA-256:
`a88406084439737d4f53241fbb75c67ed49ef9f3ab648be3cee8a75d53e5773c`. Input bundle SHA-256:
`2469151333c275a210fa4bcdec8413c211c9e01ea7896655fcc9c899c3f29ad3`. Raw telemetry, the immutable
input bundle, the exact study scripts and settings, controller log and archive are in ignored
`outputs/experiments/realism-camera-round/l4-worker-scaling/` and its parent; these are not tracked
source. The machine-derived guard-policy utility and its separately saved parameters are documented
in the [harness guide](../../../experiments/blenderproc/README.md). This short screen does not change
generic defaults or establish real-image utility.
