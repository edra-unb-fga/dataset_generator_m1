# Study index

These are retained reports, not a list of production defaults. Open a report for its exact fixture,
measurements, provenance, verdict and limitations. The [historical narrative](../EXPERIMENTS_HISTORY.md)
provides chronological context and commands. Raw output may be absent from a checkout.

| Question | Retained evidence | Status and scope |
| --- | --- | --- |
| How do appearance and camera choices affect cost and visuals? | [Profile tradeoffs](profile-tradeoffs-v1/README.md), [augmentation](augmentation-heavy-v1/README.md), [native fog](native-fog-v1/README.md), [drone screen](drone-screen-v1/README.md) | Shipped appearance catalog and optional experimental presets; results are paired, local evidence. |
| What happens to masks at edges? | [Alpha resampling](alpha-resampling-v1/README.md), [corrected pad baseline](corrected-pad-baseline-v1/README.md) | Historical correctness and baseline evidence; inspect each report for its contract. |
| Why do placement and split attempts fail? | [Landing placement](landing-placement-v1/README.md), [asset-disjoint feasibility](asset-disjoint-v1/README.md) | Diagnostic evidence; connectivity limits split feasibility. |
| How do surfaces, lighting and occlusion behave? | [Planar surfaces](planar-surfaces-v1/README.md), [surface integration](surface-integration-v1/README.md), [effect combinations](effect-combinations-v1/README.md) | Optional treatments and synthetic engineering evidence; real references and model transfer remain open. |
| What changed in execution cost? | [Background performance](background-performance-v1/README.md), [process-tree overhead](process-tree-overhead-v1/README.md), [rolling scheduler](rolling-scheduler-v1/README.md) | Local measurements, not universal budgets. |
| Which execution settings were tested? | [Execution screen](execution-screen-v1/README.md), [tuning](execution-tuning-v1/README.md), [worker scaling](worker-scaling-v1/README.md), [high workers](high-workers-v1/README.md), [12-worker retry](twelve-worker-retry-v1/README.md) | Host-specific; high-worker capacity stops and incomplete sustained retry are retained evidence, not recommended defaults. |
| What does the optional 3D harness demonstrate? | [Blender pilot](blender-pilot-v1/README.md), [execution](blender-execution-v1/README.md), [Colab screen](colab-quick-screen-v1/README.md), [L4 scaling](l4-worker-scaling-v1/README.md) | Experimental separate harness; small screens do not prove realism or general performance. |
| What happened in camera/environment studies? | [Initial partial screen](camera-environments-v1/README.md), [L4 continuation](l4-camera-completion-v1/README.md), [2D timing](linear-colab-timing-v1/README.md) | Initial 3D runs stopped by resource guards; later continuation completes selected cells, not real-world validation. |
| What did the latest exploratory realism screen show? | [Shadows, indoor, haze and 2D](realism-exploration-v1/README.md) | Historical study-only fixtures; paired masks, visual limitations and a failed haze launch retained. |
| Do reusable scene presets run outside diagnostic studies? | [Procedural scene screen](procedural-scenes-v1/README.md) | Ordinary open/outdoor/indoor jobs on L4; revision-bound images, indoor hotspots and limited sample coverage. |
| How do ground scaling, sunlight and material maps interact? | [Ground scale and material screen](ground-material-study-v1/README.md) | Optional independent mapping, verified flat-plane UV tangents, coherent/stress material variants and matched synthetic evidence. |
| How usable is the workflow? | [First-use review](first-use-review-v1.md) | Historical usability observations; verify current behavior in the product contract. |

See [scene presets](../SCENE_PRESETS.md) for current scenario controls and [roadmap](../ROADMAP.md)
for unresolved work. A historical rejection or stopped run remains useful evidence and is not a shipped
recommendation.
