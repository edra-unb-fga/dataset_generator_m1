# Continuous process-tree monitor overhead v1

Three paired landing runs compared `resource_sampling: continuous` with `resource_sampling: off`.
Every run used `builtin:appearance/current-fast`, 20 accepted 1280×1280 JPEG samples, two workers,
the same seed and source catalog, and no QA samples. Treatment order was continuous/off, off/continuous,
then continuous/off. Raw pools remain ignored.

| Pair | Continuous | Off | Paired delta | Samples | Dropped |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 55.70 s | 52.21 s | +6.68% | 54 | 0 |
| 2 | 48.73 s | 50.54 s | −3.58% | 48 | 0 |
| 3 | 54.94 s | 48.79 s | +12.61% | 54 | 0 |

The median paired delta was +6.68%, but the observed range (−3.58% to +12.61%) crosses zero and is
too variable to support a universal performance threshold. The mean continuous/off times were
53.12/50.51 seconds in this one environment. The monitor captured a three-process peak in every
continuous run.

Every paired run produced byte-identical images and mask archives plus identical geometry signatures
and annotations. The monitor therefore changed observation cost, not generated content. Keep continuous
sampling as the auditable default; use `off` only for explicit controlled comparisons. Hardware-class
baselines remain tracked separately in issue #28.

Environment: Windows 11 AMD64, 8 logical CPUs, Python 3.14.5, psutil 7.2.2. These measurements are
machine-local evidence, not a cross-machine guarantee.
