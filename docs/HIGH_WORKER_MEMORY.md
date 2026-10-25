# High-worker capacity and phase memory estimates

Follow-up scope: compare6/12 workers at1–2 native OpenCV threads, then cautiously consider16 before24.
Keep1280² heavy pad generation, standard background mix, masks/QA, renderer and source distributions
unchanged. Record repeated six-worker evidence plus guarded capacity results. Do not call an aborted
pool a throughput result, reduce dimensions to make a stress case finish, or extrapolate a generic
hardware recommendation from this host.

The12-worker full-concurrency ramp reached a2.5 GiB available-memory floor and was stopped. Because
that first escalation failed its headroom condition,16/24 and12×2 are not attempted on the current
host state. No other applications are closed or modified to make room. Raw partial pool/monitor data
remain ignored. Higher-worker trials need a quieter/larger-RAM environment and the same watchdogs.

## Estimator correction

The preceding v2 model summed expired graph outputs and mutually exclusive synthesis/render/evidence
phases. The v3 model uses the renderer's last-consumer release schedule, operation-specific scratch,
scalar/RGB precision propagation, per-asset correlated source/cover dimensions and the maximum worker
phase. Actual source foreground rotation/resize expansion is retained. Runtime reserves stay256 MiB
per process; explicit returned-result/cache/native reserves remain, with20% headroom.

Predictions are process-tree RSS planning upper estimates. Summed RSS repeats fork-shared pages;
Linux PSS/USS are recorded independently to show physical/private memory. PSS is sampled once per
second; the global available-memory floor and swap checks are polled at0.1 seconds. Neither sampled
guards nor RAM budgets are OS hard allocation limits. The new model is validated against retained
RSS and independently traced recipe arrays, without claiming that all native/effect configurations
have a perfect bound. Existing runtime measurements are not silently retuned to another metric.

No renderer, scheduling, effect, geometry/annotation, profile default or native library changes belong
in this follow-up. Automatic worker counts may increase where a complete phase estimate fits the
budget. More machines/workloads remain #28; approximate smoothing and scheduler design remain future
planning decisions. The retained report records measurements, model/source hashes, capacity stop and
reproduction commands.
