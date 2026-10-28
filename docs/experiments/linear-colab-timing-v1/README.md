# Linear compositing: paired Colab CPU timing

This exploratory production-path comparison used the CPU of a Colab L4 runtime at 640², four
workers with one native thread each, forced procedural occlusion, and the existing pristine surface
profile. It performed three alternating repetitions of four measured images per mode, with two
separate warmups per cell. The same four measured slots recur in every repetition; this is timing
repeatability, not a diverse-scene study. All 24 measured images were accepted and the paired
geometry, annotations and mask signatures matched.

| Repetition | Legacy images/s | Linear-sRGB images/s | Linear change |
| --- | ---: | ---: | ---: |
| 1 | 2.110 | 2.026 | -3.99% |
| 2 | 2.099 | 2.024 | -3.56% |
| 3 | 2.109 | 1.973 | -6.45% |

Median throughput was 2.109 images/s for legacy and 2.024 images/s for linear-sRGB; the median
paired change was -3.99%. Generation includes pool writes; preparation is recorded separately.
This is not an end-to-end Blender comparison or a visual-realism verdict. A separate prior visual
screen found no clear broad realism win for linear composition, so it remains opt-in.

The CPU timing study's machine-derived limits were 5.30 GiB minimum available host memory,
40.94 GiB summed process-tree RSS and 16 MiB system-wide swap-out. The monitored command completed
with 0 swap-out and approximately 0.94 GiB sampled peak summed RSS. The guard configuration is
recorded with its measured basis; summed RSS can double-count shared pages. The study explicitly
recorded preflight receipts for the requested uncalibrated experimental modes; unexpected warning
codes still fail the run. No local-CPU guard was weakened after its earlier stop.

The standalone L4 runtime stopped automatically following checksum-verified retrieval; raw data,
the input package and execution logs are ignored experiment outputs. Result archive SHA-256:
`23efdc2566335591a96e815d692d8bedb69d3d826c89775821086f176156268a`. The separately tracked
`experiments/planar/linear-compositing-timing.json` defines the baseline study and its conservative
local guards; a new matrix may explicitly specify machine-appropriate guards before starting a fresh
study. The screenshots and note on visual interpretation remain in
[the earlier camera/effects report](../camera-environments-v1/README.md).
