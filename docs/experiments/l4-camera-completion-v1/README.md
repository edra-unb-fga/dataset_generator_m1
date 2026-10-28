# L4 camera and environments evidence

Open [the standalone report](index.html). It embeds visual evidence and is usable offline.
`compact.json` contains the automated validation summary; [review.md](review.md) records the visual
assessment and its limits. The report records both an initial and an independent visual review; no real-image/model evaluation was available.
Raw scenes, handoff archives, input bundles and telemetry remain in ignored experiment outputs.

Rebuild from the retrieved and safely extracted raw bundle (replace `$STUDY` with its local path):

```sh
uv run python scripts/analyze_l4_camera_completion.py "$STUDY/retrieved" "$STUDY/validation"
uv run python scripts/validate_camera_coco.py --results "$STUDY/retrieved/results" --validation-dir "$STUDY/validation"
uv run python scripts/report_l4_camera_completion.py --validation-dir "$STUDY/validation" --review docs/experiments/l4-camera-completion-v1/review.md --output-dir docs/experiments/l4-camera-completion-v1
```

The 128-sample comparison can be rebuilt with `scripts/compare_camera_samples.py` using the
32- and 128-sample cell roots; retain the separately generated `high-quality-summary.json`.
The 2D timing table is included when `validation/2d-timing-summary.json` is present; it is the
`result/study/summary.json` member of the separately retrieved 2D archive. Source/input and archive
hashes, failed attempts, the dynamic guard basis and the exact run definitions remain in that evidence.
The captured [study matrices and controllers](../../../experiments/blenderproc/studies/l4-camera-completion/README.md)
provide the exact tested definitions and rerun instructions.
