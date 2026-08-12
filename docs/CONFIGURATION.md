# Composable configuration and guided CLI

The public configuration is one schema-v2 composer. It selects versioned subject profiles and may contain
strict inline values for a particular run. Resolution produces one immutable profile, reference graph,
source-hash set, applied-override record, and contract hash before any output directory is created.

Background recipes and background mixing are separate public subjects: the first selects available typed
synthesis DAGs, while the second controls their sampling weights. They resolve into one internal renderer
contract, so users can tune the mix without forking algorithm definitions.

## Start-to-results workflow

```powershell
uv run python -m dataset_generator_m1 start
uv run python -m dataset_generator_m1 start --config configs/my-landing.yaml
```

`start` is the recommended interactive entry point. It checks environment readiness and incomplete runs,
separates validated `configs/*.yaml` files from shipped examples, copies an example into `configs/` before
customization, and suggests a collision-free destination under `outputs/runs/<composer>/<timestamp>`.
Essentials show family, image count, appearance, dimensions, workers, destination, warnings, disk use, and
**Estimated time remaining**. Advanced keeps every typed subject and documented effect reachable.

The journey always saves a composer before preparation. It reviews the immutable contract, performs one
full preflight/probe, requests any warning receipt, and then requires a separate final confirmation. The
prepared result is passed directly into generation. Afterward, a persistent results dashboard can open QA,
inspect audit evidence, export YOLO detection or segmentation, resume an interrupted run, or start another run. Back and cancel choices
are available before generation. Non-TTY callers receive equivalent atomic commands and are never prompted.

## Discover and inspect

```powershell
uv run python -m dataset_generator_m1 catalog list
uv run python -m dataset_generator_m1 catalog show builtin:appearance/realistic-heavy
uv run python -m dataset_generator_m1 resolve --config examples/configs/landing_minimal.yaml
```

`catalog list --config path/to/composer.yaml` includes promoted workspace bundles next to that composer.
Built-in bundles contain executable `profile.yaml`, machine-readable `metadata.json`, and a human-readable
`README.md`. A path-only YAML profile is permitted but reported as local and undocumented.

## Create a composer in the cockpit

```powershell
uv run python -m dataset_generator_m1 configure `
  --family landing `
  --output examples/configs/my-landing.yaml
```

The command writes a valid composer before opening the menu. Its summary shows every referenced subject,
current warnings, an evidence-backed ETA range, and the suggested preflight command. From the menu:

- choose one of the six reviewed appearance profiles;
- browse any other subject and select a built-in, workspace, relative-path, or absolute-path profile;
- set run count, seed, worker policy, output dimensions, and format;
- build an inline background, foreground, or final effect stack;
- read the file-backed description for every selectable effect.

`realistic-heavy` is the standard default. `current-fast` is the explicit performance-oriented alternative.
Legacy, RandomFog-heavy, no-appearance, and stress profiles remain selectable. Slow valid choices are warned,
not removed.

JSON and quiet modes never prompt; they save the default or explicitly selected appearance and return the
resolved summary:

`configure` remains the focused authoring command. Use it when you want to edit a composer without continuing
through preflight and generation; use `start` for the complete guided journey.

```powershell
uv run python -m dataset_generator_m1 configure --family landing --output examples/configs/my-landing.yaml --output-format json
```

## Advanced effects and promotion

The advanced builder validates effect type, stage, stable ID, probability, and JSON parameters through the
same production filter path. Inline effects stay visible in the composer and are included in its contract
hash. In particular, `AtmosphericFog` exposes `linear`, `diagonal`, and `radial` depth modes while RandomFog
remains a separate patch-based effect with a high-cost warning.

After visual/performance review, promote one inline stage explicitly:

```powershell
uv run python -m dataset_generator_m1 catalog promote `
  --config examples/configs/my-landing.yaml `
  --stage final `
  --id my-camera
```

Promotion creates `profiles/workspace/appearance.<stage>/<id>/` with all three bundle files. It never silently
rewrites the composer; replace the inline stack with the returned workspace reference after reviewing the
generated metadata. Resolution-equivalence is tested.

## Override precedence

Use a versioned override file for experiments and repeated `--set` for deliberate leaf changes:

```powershell
uv run python -m dataset_generator_m1 generate `
  --config examples/configs/my-landing.yaml `
  --overrides experiments/run-overrides.yaml `
  --num-images 100 `
  --workers auto `
  --set run.num_images=200 `
  --set execution.workers=4 `
  --output-dir outputs/my-landing
```

Precedence is profile references, composer inline values, override file, common CLI options, then repeated
typed `--set` leaves; later `--set` values win. Unknown paths, mapping-valued `--set`, and values rejected by
the final typed profile fail before output creation. Override files are hashed into provenance. The resolved
values and applied leaf overrides are saved in `run.json`.

Use `resolve` with the same `--overrides` and `--set` arguments to inspect the exact contract before running.
Use `preflight` to obtain disk, warning, probe, and ETA evidence; warning receipt semantics are documented in
[PREFLIGHT.md](PREFLIGHT.md).

## Versionable user composers

Treat `configs/*.yaml` as reviewed, versionable user source. Use `configs/local/` for ignored scratch composers,
temporary comparisons, and cockpit experiments. Promote a local composer into the tracked root only after
resolving it, reviewing its references/overrides, and choosing a stable name. Generated pools and exports do
not belong under `configs/`.
