# Paired physical effects screen

This exploratory L4 screen uses six previously seen synthetic scene intents and one deliberately closer diagnostic view. Nine saved cells vary a moderate shared wear recipe, pad roughness, overcast lighting and combinations, with a separate caster diagnostic. Inputs are paired within BlenderProc; they are not matched to the separate 2D study and are not independent real data. Wear changes albedo, roughness and bump maps together. Overcast varies illumination, not a cast shadow. The caster diagnostic intentionally revisits a known artifact and is not a recommended production setting.

The 640-pixel, 32-sample scenes use saved workers/threads and a hardware-derived host/GPU guard; `budget.json` sets the single-phase time limits. Keep the exact portable input bundle and its bootstrap next to the run evidence. From the repository root:

```sh
python3 experiments/blenderproc/studies/effect-combinations/supervisor.py run \
  --phase development --bundle /absolute/path/input.tar.gz --output /absolute/path/output \
  --session unique-name --colab /absolute/path/to/colab
```

The supervisor packages and verifies evidence and stops the runtime. Its separate watchdog attempts a stop at the saved deadline; network, host or credential failures can still prevent recovery or release. Run as a persistent logged process if the controlling agent might disconnect. After extracting the retrieved archive, build the portable report:

```sh
.venv/bin/python scripts/report_physical_combinations.py --input /path/to/extracted/results --output /path/to/report.html
.venv/bin/python scripts/enhance_effect_report.py --input /path/to/report.html --output /path/to/filtered.html
```

Quantitative RGB differences measure visual change, not realism, utility or a detector outcome. The individual and combined cells have different interpretations; inspect target crops, full scenes, realized parameters and masks together.
