# Guarded production coherent-scene comparison

This study compares each family's existing `realistic-heavy` appearance and
standard scene with a selected, opt-in scene/appearance pair. Both use the same
production asset catalog, seed, resolution and object sampling. The runner checks
the complete geometry, annotation and visible/full mask signature for each pair.
The candidate cells have their own probabilistic effects; they do not share the
baseline's appearance random streams. No family default is changed.

The current saved local policy retains its 2 GiB minimum available-memory reserve and
adaptive process-tree RSS limit; 16 MiB of system-wide swap-out now records a warning.
Use `experiments/foreground-context/strict-benchmark-policy.json` for the explicit
legacy stop behavior when controlling benchmark conditions. Historical runs retain
their recorded policies and should not be silently retried under different limits.
The driver uses one worker and one native thread; each new directory records the
actual guard basis, policy bytes, effective profiles, source hashes, command, driver
hash, resource trace, pool inspection and generation wall time. A guard stop is an
incomplete run, not evidence of throughput or quality. Never weaken guards
automatically after a stop. Re-run with a fresh output directory:

```sh
uv run python experiments/foreground-context/coherent-study/run.py \
  --output-dir outputs/experiments/coherent-candidate-reproduction \
  --treatment coherent-candidate --samples 67 --seed 20261102 --size 640
uv run python experiments/foreground-context/coherent-study/run.py \
  --output-dir outputs/experiments/coherent-refined-reproduction \
  --treatment coherent-refined --samples 67 --seed 20261102 --size 640
```

`--families landing-pad landing manometro` selects any unique subset; `--policy`
accepts another saved guard policy. Count is limited to 1–100 per family per cell.
Each complete run generates both baseline and candidate images. Timing is a single
ordered pass without separate warmups; preparation is separate. Use alternating,
warmed repeats before treating timings as a benchmark. The runs use the same asset
catalog and are neither an asset holdout nor real-image or detector evaluation.

The first candidate selects `builtin:scene/coherent-candidate` and
`builtin:appearance/coherent-candidate`; the refinement selects
`builtin:scene/coherent-refined` and `builtin:appearance/coherent-refined`.
Read their bundle YAML for exact settings. The refinement reduces wear and adds
mild common shade; the shade cannot produce a contact shadow.

## Historical local runs

The first guarded screen used seed 20261031, four images per cell and a 900-second
timeout; the first candidate gallery used seed 20261102, 67 images per cell and the
same timeout. The refined four-image screen reused the first screen's seed. Their
raw pools, drivers and resource logs are retained respectively under ignored
`outputs/experiments/coherent-2d-initial`, `coherent-2d-gallery`, and
`coherent-2d-refined-screen`. The consolidated runner above reproduces the study
configuration but is a later driver, not the original byte-identical script; its
default saved-policy timeout is 1800 seconds. The old drivers and their SHA-256:

| Input | SHA-256 |
|---|---|
| Initial driver | `588c3220d8b6a4ba9015585aec0e915bdcfebfc36a96b0b967e5c82bda7e2e5e` |
| Gallery driver | `ba71bbb8c767c82520c40e1666c59e551eb06fd1823281726227ade00798d22a` |
| Refined screen driver | `a3bec2fcd18b5f26fbdbc23bcac3876bce434df06d49b46d0b2feb5dff8a54fe` |
| Historical monitor, all three runs | `6854b82f71e9e215a63ac92847fc98cd214ad57d5a95fd3191a24da364909c9e` |
| Scene candidate profile | `f5f84821fcc9211198a6b2a21dab348e68861df46db5c83f00e35c88c83c3177` |
| Appearance candidate profile | `97051728224072fa712d5053cb9ce13ef01194ebda2b6c4471dc154c61ce99e6` |
| Scene refined profile | `0c94309470605545910399c663c7a895164fa80a598d92a8156e366e86cdbc41` |
| Appearance refined profile | `8be646e4fe817783aae7265ad19e090c31b8580692e397a8840d2c232b49b962` |
| Current saved local policy | `7571521317b9497089158b2cd530c7e7f5082a434b131c2da4cc09809fca00d0` |

Source and software fingerprints for each resolved cell, as well as image-level
seeds, scene effects, signatures and mask evidence, remain alongside the raw pools.
The consolidated runner subsequently completed `coherent-2d-refined-gallery` with
67 pairs per family, seed 20261102 and 640px output. Every cell's signature matched
the corresponding first gallery baseline. The candidate gallery and refined gallery
each contain 201 candidate and 201 baseline images. The refined run's guard recorded
427,347,968 bytes peak process-tree RSS, 3,793,666,048 bytes minimum available memory
and no additional system-wide swap-out. The two 67-pair studies reported these
generation-only rates (images/s); they are single ordered passes, not robust
benchmark estimates:

| Family | First baseline | First candidate | Refined baseline | Refined candidate |
|---|---:|---:|---:|---:|
| Landing pad | 2.463 | 1.767 | 2.295 | 1.771 |
| Landing | 2.412 | 2.026 | 2.438 | 2.028 |
| Manometro | 2.692 | 2.367 | 2.532 | 2.469 |

In the initial four-pair crop review, the first candidate created visible oval marks
on landing targets; refined wear reduced those marks. The foregrounds still appeared
flat in those samples. This small qualitative screen does not qualify a family default.

## Forced-shade diagnostic

`strong-shade.json` compares the same refined wear, local context and gain field
with and without a forced, strong scene-wide shade. It disables normal capture
effects and forces wear, so it is a diagnostic ablation rather than a full-profile
comparison. Shade placement is sampled independently and may miss every target;
inspect the scene evidence and images before claiming a crossing. The paired
geometry/mask checks still apply. For the 640px landing-pad development screen:

```sh
uv run python scripts/guarded_effect_combinations.py \
  --config experiments/foreground-context/coherent-study/landing-pad-640.yaml \
  --matrix experiments/foreground-context/coherent-study/strong-shade.json \
  --policy experiments/foreground-context/coherent-study/one-worker-policy.json \
  --phase development --samples 4 \
  --output-dir outputs/experiments/coherent-strong-shade
```

The local four-pair landing-pad diagnostic completed with equal geometry and mask
signatures. Target-region mean absolute RGB differences from the control ranged
from 8.01 to 15.51 on the 0–255 scale; this is an effect size, not a realism score.
Visual review found broad smooth darkening but no clear shadow edge crossing a target
or convincing contact. Results, traces and the paired sheet are retained under the
ignored output path above. The shade is an uncalibrated field, not a cast or contact
shadow model.

## Directional edge diagnostic

`directional-shade.json` adds two deliberately strong slab treatments to the same
refined-look control. Both use fixed width .25, centered offset 0 and strength .6;
the hard edge is vertical in scene coordinates and the soft edge uses 30 degrees
and softness .06. Centering was chosen to exercise target crossings in the known
development scenes; random placement in ordinary use does not guarantee a crossing.
The two variants differ in angle as well as softness, so they do not isolate edge
softness. Capture effects are disabled and wear is forced. The slab is an infinite,
qualitative field, not a caster or contact-shadow model.

```sh
PYTHONPATH=src uv run python scripts/guarded_effect_combinations.py \
  --config experiments/foreground-context/coherent-study/landing-pad-640.yaml \
  --matrix experiments/foreground-context/coherent-study/directional-shade.json \
  --policy experiments/foreground-context/coherent-study/one-worker-policy.json \
  --phase development --samples 4 \
  --output-dir outputs/experiments/coherent-directional-shade-reproduction
```

The local 640px run completed all 12 images with valid pool inspections and the
same geometry/annotation/mask signature in all three variants:
`dc294da57f15ef3a4bf36a6414dc8d438eb4a8ddb1409c945c4543b47eb8575d`.
Visual inspection shows the hard edge crossing the target in slots 0, 1 and 2;
the edge is stark and procedural. Target-region mean RGB absolute differences
versus control are 19.88–42.75 for hard and 15.09–30.34 for soft on the 0–255
scale. JPEG decoding and mask thresholds influence these measures. This is a
four-scene visual/effect-size check, not a realism, detector-transfer or throughput
claim. The guarded run recorded peak process-tree RSS 329,383,936 bytes, minimum
available memory 4,022,296,576 bytes and zero additional swap-out. Its raw pools,
profile/source identities, full metrics and portable paired report are retained in
ignored `outputs/experiments/coherent-directional-shade-local/study/`.

The local run used Python 3.13.16, NumPy 2.5.1, OpenCV 5.0.0.93,
Albumentations 2.0.8 and Pillow 12.3.0. Key SHA-256 source fingerprints:

| Input | SHA-256 |
|---|---|
| models.py | `ef2b6732e7b9383e8546923d9736c75f5d347bb50d1b563fa2f833efa107e4aa` |
| surface_effects.py | `9df4743b899f73346871a6a7b463d8125b0d755413a0abdd8c8d18a5b9ecac8e` |
| scene.py | `06749b52c4e409d9ebc200a9769e2dd79f0de60f1d7b6225c65009ed8f6bae4a` |
| memory_planning.py | `a8fedecf7002b6d2c162384fd32e39626417cb4bd5d9610b85aa75b920c4ce0f` |
| directional-shade.json | `c247e5ed0caee79b59d9cd88a8773c0d8e8d5034271840104093231fad5cae01` |
| one-worker-policy.json | `c406acc5d46e960ae6705456647c9be9f6bf134e40b912f14250c1cdfeaa3db2` |
| study_effect_combinations.py | `9982b2e05ee789ae8c4287e568614ab3d34d82be54ee2431bf7a2911144f6e54` |
| guarded_effect_combinations.py | `a4e89d0fc043dff2756a51953985d1fa7f3cf33392e249e85989ecff022ccd04` |

An earlier attempted launch failed validation before generation because the shared
editable environment resolved a different checkout. The recorded successful run
uses `PYTHONPATH=src`; the failed output directory is retained separately.

## Natural directional-shade screen

Three more guarded runs each produced 12 paired baseline/directional scenes at
640px, one for each maintained family. All images use the same refined-look
control as the forced diagnostic and disable capture effects. The directional cell
samples activation probability .75, strength [.2, .65], width [.08, .42], softness
[0, .09], offset [-.45, .45] and angle [0, 360] degrees. Separate development
seeds (20261102 landing-pad, 20261104 manometro, 20261106 landing) provide 36
parameter draws; this is a deliberately bounded synthetic screen, not a real-image
holdout. A shade may be inactive or miss targets. Effects and exact per-image
parameters appear in the gallery metadata.

| Family | Applied / 12 | Applied with target MAE > .05 / applied | Paired signature | Peak RSS bytes | Minimum available bytes |
|---|---:|---:|---|---:|---:|
| landing-pad | 9 | 6 / 9 | `6a343fd53ae78fc3673ff5154ecfc1ca8712b28aeb764b74a31d3e5346161150` | 329605120 | 4072542208 |
| manometro | 9 | 4 / 9 | `6718b260372b0f2986a3c4b645a2c6a791215de5baacc9e2541bee34a90d89cb` | 309927936 | 4088750080 |
| landing | 8 | 4 / 8 | `4c69f26f1b2ba6559181321ce3f1b8f12d66d2bb0205cff4fca32b7b1efac098` | 298356736 | 4124127232 |

Each family completed 24 images, all six pools passed inspection, and each pair's
geometry/annotations/masks matched its baseline signature. No run recorded
additional swap-out. The MAE threshold only indicates a decoded-image difference
inside the union of target masks; it does not identify an edge crossing. Angles,
widths and softness vary, but the same straight infinite-slab motif repeats;
several visible stripes look procedural, including manometro scenes 1 and 10.
Some treatments miss all targets. The 36-pair screen neither validates natural
lighting nor supports changing a default.

The portable 72-image review with per-image metadata, filters, keyboard navigation,
full-screen viewer and original images is in ignored
`outputs/experiments/coherent-directional-natural-gallery/index.html`. Its
`manifest.json`, `images/`, and `profiles/` must stay together. Source pools,
local reports, output signatures, guard traces and study identities remain in
`outputs/experiments/coherent-directional-natural-{landing-pad,manometro,landing}`.
Use the same guard and fresh output directories when reproducing, substituting each
family's config and matrix:

```sh
PYTHONPATH=src uv run python scripts/guarded_effect_combinations.py \
  --config experiments/foreground-context/coherent-study/landing-pad-640.yaml \
  --matrix experiments/foreground-context/coherent-study/natural-directional-shade.json \
  --policy experiments/foreground-context/coherent-study/one-worker-policy.json \
  --phase development --samples 12 --output-dir outputs/experiments/natural-landing-pad-reproduction
```

The same command uses `manometro-640.yaml` with
`natural-directional-shade-manometro.json`, and `landing-640.yaml` with
`natural-directional-shade-landing.json`. After the three completed runs, collect
with `collect_directional_gallery.py --study FAMILY OUTPUT ... --output-dir REVIEW`
and build `scripts/build_scene_review_gallery.py REVIEW/manifest.json --output
REVIEW/index.html`. Inputs and code are local and no default was promoted.

| Additional input | SHA-256 |
|---|---|
| landing-pad-640.yaml | `0e7932d4a505cf32cf37245e600482e505493f99934a8410deaa3e3d67f390a2` |
| manometro-640.yaml | `64e48dd512af788d81ef5903f1bfab7c055822a7477b3b4359f312e0cb80db60` |
| landing-640.yaml | `bb13f70548619df4608630ba46dd95072e064ce2cc5f9c44bdd9e6e434fa18fc` |
| natural-directional-shade.json | `cc895162a579b87f92121add7b253d0a8bab33f9fbde9d79e6d5c9d4a786f240` |
| natural-directional-shade-manometro.json | `c05c58ea2cd06880c9d5a951ac3ba224ead324b43206bd583ab49ca08d184015` |
| natural-directional-shade-landing.json | `64179c7b2464bac055a3d1ba535c6f93f4ee38f441c667a2a70743cde35e7624` |
| collect_directional_gallery.py | `1f1124d0b48d3cba89f843ea3cd91e4e74f689d8577a25ef114371bd9b5e7dc2` |
| build_scene_review_gallery.py | `7c99b8d69c5a244a16a5259645c2548111737eae7ac8efaf44c0ed361aa323dd` |

The code and policy hashes listed in the preceding section also apply to these runs.

## Schema bounds follow-up

After the directional ablation and natural-sampling runs above, the schema was
updated to constrain both endpoints of each range. Runtime also requires ascending
pairs, a cross-element constraint not expressed by the generated JSON Schema. The
original screen's `models.py` fingerprint above is retained as the code that
produced those images; the following identifies the later schema and runtime fix:

| Input | SHA-256 |
|---|---|
| models.py after schema bounds | `97e32c02585160aa6dde656ee7c645b5b55dbe5c39c8a47adec31083c3db4c65` |
| composer.schema.json | `35c6e41ce84219e26a8eca00f45e90e2ce992d7888277e1af2abfacddfb27e6c` |
| resolved-profile.schema.json | `eb400149b9bfb094a1260152c37e7de35ec883a86dadda40da7ce44325067446` |
| test_directional_shade.py | `281544f1d6d8ecb9e0e6a0bfb747e022514e784d741180980002b1e39b2fb234` |

## Directional shade with the full refined appearance

`builtin:scene/coherent-directional` combines the refined scene's context,
elliptical shade and the same natural directional settings used in the preceding
screen. The production runner pairs it with the existing full
`builtin:appearance/coherent-refined`, including probabilistic wear, exposure,
motion blur and compression. The baseline uses each family's existing standard
scene and realistic-heavy appearance. These cells therefore differ in more than
shade; their visual differences do not isolate any one effect. Neither profile is
promoted as a default.

A guarded local run produced 20 baseline/candidate pairs for each family at 640px,
using seed 20261108, distinct from the earlier development seeds. All six pools
passed inspection and the paired geometry/annotation/mask signatures matched:

| Family | Directional shade applied / 20 | Paired signature |
|---|---:|---|
| landing-pad | 13 | `edbbb8d7060aac631f5e77652330d066b9360451fa7fb32de0f2ee58bcc9e1a9` |
| landing | 13 | `7dd79f193233fedca5266eb59cb65b2acb9adc13cf9d007b2b599e1472499d48` |
| manometro | 15 | `e72af233413c59a2a25f586995ffc505ce120dee651517c25993a9aea4038c4d` |

The full candidate capture stack was exercised: exposure, motion and compression
were applied in 7/6/8 landing-pad, 7/6/8 landing, and 6/5/7 manometro images,
respectively. The same seed is used across families and some backgrounds and
lighting draws repeat, so these are not 60 independent lighting conditions. The
same source asset catalog is reused; the new seed does not establish unseen-asset
or real-image performance. The visible straight bands still look procedural in
some cases, such as landing slot 10 and manometro slot 17. This screen does not
establish a detector benefit or qualify a default.

The 120-image paired, filterable, full-screen review is retained with its manifest,
images and effective profiles in ignored
`outputs/experiments/coherent-directional-production-gallery/index.html`. The raw
pools, source identities, commands, resource trace and inspection results remain
in `outputs/experiments/coherent-directional-production/`. The guard recorded a
370,917,376-byte peak process-tree RSS, 4,040,593,408-byte minimum available memory,
and zero additional swap-out; the full command took 73.24 seconds. This one
ordered pass is not a performance benchmark.

```sh
PYTHONPATH=src uv run python experiments/foreground-context/coherent-study/run.py \
  --output-dir outputs/experiments/coherent-directional-production-reproduction \
  --treatment coherent-directional --samples 20 --seed 20261108 --size 640 \
  --policy experiments/foreground-context/coherent-study/one-worker-policy.json
```

The key SHA-256 identities at this run were:

| Input | SHA-256 |
|---|---|
| coherent-directional scene profile | `21efefced1e39b23d4c91e84ec4a329d038da4542131c3102ae288704412ec8e` |
| coherent-directional scene metadata | `52d0d749ce4e91106294b84edcf5c4783dc9503c91fff6e919d4fcffcc025e0d` |
| coherent-refined appearance profile | `8be646e4fe817783aae7265ad19e090c31b8580692e397a8840d2c232b49b962` |
| coherent-refined appearance metadata | `a2d558896a5400bf35fe6cf1c796361c6a6bdbd0531b0089478ff53d3ecadf74` |
| study runner | `eef7ff674a1b3d57cc8220c1ba067ba3ad5229dff3cc151abc2d9e238f423a85` |
| models.py | `97e32c02585160aa6dde656ee7c645b5b55dbe5c39c8a47adec31083c3db4c65` |
| surface_effects.py | `9df4743b899f73346871a6a7b463d8125b0d755413a0abdd8c8d18a5b9ecac8e` |
| scene.py | `06749b52c4e409d9ebc200a9769e2dd79f0de60f1d7b6225c65009ed8f6bae4a` |
| one-worker policy | `c406acc5d46e960ae6705456647c9be9f6bf134e40b912f14250c1cdfeaa3db2` |

The software versions match those recorded for the forced diagnostic. The
complete source and asset identities are in the saved effective profiles and pools.

## Finite directional-shade screen

The guarded `coherent-shape-screen` run compared three forced-shade conditions
for each family: four matched slots per family at 640px with run seed 20261108.
All three conditions use `builtin:scene/coherent-directional` and the full
`builtin:appearance/coherent-refined`. The raw variant named `baseline`, displayed
in the saved gallery as **band**, is forced directional shade, not the
standard-scene/realistic-heavy baseline from the preceding production comparison.
The other variants are `rectangle` and `ellipse`. All conditions override the
same directional settings: probability 1, strength [.45, .65], width [.15, .3],
softness [.01, .06], offset [-.15, .15], and the preset's angle [0, 360] degrees.
Finite conditions additionally set their respective `shape`, length [.45, .9],
and longitudinal offset [-.15, .15]. Each cell uses one worker and one native
thread. The same run seed across families and four distinct sample slots do not
constitute four independent run seeds or independent family lighting draws.

The 36-image screen completed all nine inspected pools with matching
geometry/annotation/mask signatures across the three conditions within each
family. The guard recorded 3,901,046,784 bytes minimum available memory,
351,240,192 bytes peak process-tree RSS, and zero new swap-out. Finite ends and
rounded silhouettes add variety, including manometro slot 2; the rectangle there
also looks conspicuously geometric. Several finite ends lie outside the camera
crop. These forced examples do not establish realism, target-readability impact,
or a suitable frequency for production. No default is promoted. Native images,
profiles, manifest and visual notes are in ignored
`outputs/experiments/coherent-shape-screen-gallery/`, with the guarded run's
profiles, resource traces and source identities in
`outputs/experiments/coherent-shape-screen/`.

The run used a temporary adaptation of `run.py`; its exact recorded source is
retained as `outputs/experiments/coherent-shape-screen/driver-source.py` (SHA-256
`812a299c7380a1c1936699d1b533e87ad3ae1404d383e2abcd59e8ae9eb6d6e1`). It
must be placed in the study directory for its repository-root discovery to work.
The commands below recreate that adaptation from the tracked runner without
requiring the ignored historical output, and write only to fresh output locations.
Run from the repository root with the finite-shape implementation installed and
at least 2 GiB available; do not weaken the saved 16 MiB swap-out guard after a
stop. The generated driver is temporary and can be removed after completion.

```sh
python3 - <<'PY'
from pathlib import Path

source = Path('experiments/foreground-context/coherent-study/run.py')
target = source.with_name('shape-screen-reproduction.py')
if target.exists():
    raise FileExistsError(target)
text = source.read_text()
changes = [
    ("for variant in ('baseline', 'candidate'):",
     "for variant in ('baseline', 'rectangle', 'ellipse'):"),
    ("if variant == 'candidate':", "if True:"),
    ("        values['run'].update(seed=seed, num_images=samples)",
     """        shade = values['scene']['lighting']['directional_shade']
        shade.update(probability=1, strength=[.45, .65], width=[.15, .3],
                     softness=[.01, .06], offset=[-.15, .15])
        if variant != 'baseline':
            shade.update(shape=variant, length=[.45, .9], longitudinal_offset=[-.15, .15])
        values['run'].update(seed=seed, num_images=samples)"""),
]
for before, after in changes:
    if text.count(before) != 1:
        raise RuntimeError(f'Runner changed; cannot reproduce replacement: {before}')
    text = text.replace(before, after)
target.write_text(text)
PY
PYTHONPATH=src uv run python experiments/foreground-context/coherent-study/shape-screen-reproduction.py \
  --output-dir outputs/experiments/coherent-shape-screen-reproduction \
  --families landing-pad landing manometro --treatment coherent-directional \
  --samples 4 --seed 20261108 --size 640 \
  --policy experiments/foreground-context/local-cpu-policy.json
PYTHONPATH=src uv run python scripts/collect_2d_review_gallery.py \
  outputs/experiments/coherent-shape-screen-reproduction \
  outputs/experiments/coherent-shape-screen-reproduction-gallery
PYTHONPATH=src uv run python scripts/build_scene_review_gallery.py \
  outputs/experiments/coherent-shape-screen-reproduction-gallery/manifest.json \
  --output outputs/experiments/coherent-shape-screen-reproduction-gallery/index.html
rm experiments/foreground-context/coherent-study/shape-screen-reproduction.py
```

The runner records the actual policy, guard basis, command, copied driver, resolved
profiles and sample identities in the reproduction directory. Compare those identities
when exact source or asset provenance matters. As elsewhere in this study, ordered
single-pass timing is not a benchmark and a stopped run is incomplete evidence.

### Matched unshaded control

A subsequent guarded run generated four `unshaded` slots per family using the
same run seed, size, coherent-directional scene and coherent-refined appearance.
The only resolved profile difference from the `baseline` band condition was the
absence of `directional_shade` (disabled with probability 0). Existing scene
lighting, the separate probabilistic soft elliptical environmental shade, and all
appearance and capture effects remain enabled; `unshaded` means no *directional*
shade, not an unlit scene. All three new pool inspections were valid, and each
family's full geometry/annotation/mask signature matched the band, rectangle and
ellipse cells. The run's minimum available memory was 4,148,887,552 bytes, peak
process-tree RSS 335,663,104 bytes, and new system swap-out zero. It used the
same 2 GiB reserve and 16 MiB swap-out guard. The 12 images and effective profiles
are included as `unshaded` in the existing 48-image shape gallery; the original
36 images remain present. Raw evidence is in ignored
`outputs/experiments/coherent-shape-unshaded/`, with a standalone collected copy
in `outputs/experiments/coherent-shape-unshaded-gallery/`.

To reproduce the control, run the preceding shape-screen reproduction first and
then the following from the repository root. The generated driver goes under
`/tmp`, uses the current checkout as its root, and preserves the guarded runner's
worker and profile behavior. The generated control uses fresh output directories.

```sh
python3 - <<'PY'
from pathlib import Path
source = Path('experiments/foreground-context/coherent-study/run.py').read_text()
changes = [
    ("ROOT = Path(__file__).resolve().parents[3]", f"ROOT = Path({str(Path.cwd())!r})"),
    ("for variant in ('baseline', 'candidate'):", "for variant in ('unshaded',):"),
    ("if variant == 'candidate':", "if True:"),
    ("        values['run'].update(seed=seed, num_images=samples)",
     """        shade = values['scene']['lighting']['directional_shade']
        shade.update(probability=0, strength=[.45, .65], width=[.15, .3],
                     softness=[.01, .06], offset=[-.15, .15])
        values['run'].update(seed=seed, num_images=samples)"""),
]
for before, after in changes:
    if source.count(before) != 1:
        raise RuntimeError(f'Runner changed; cannot reproduce replacement: {before}')
    source = source.replace(before, after)
target = Path('/tmp/coherent-unshaded-reproduction.py')
if target.exists():
    raise FileExistsError(target)
target.write_text(source)
PY
PYTHONPATH=src uv run python /tmp/coherent-unshaded-reproduction.py \
  --output-dir outputs/experiments/coherent-unshaded-reproduction \
  --families landing-pad landing manometro --treatment coherent-directional \
  --samples 4 --seed 20261108 --size 640 \
  --policy experiments/foreground-context/local-cpu-policy.json
PYTHONPATH=src uv run python scripts/collect_2d_review_gallery.py \
  outputs/experiments/coherent-unshaded-reproduction \
  outputs/experiments/coherent-unshaded-reproduction-gallery
rm /tmp/coherent-unshaded-reproduction.py
```

Before interpreting a reproduced pair, compare each unshaded record's `signature`
with all three same-family shape records, inspect each pool, and compare resolved
profiles after removing the band profile's `directional_shade` field. This is a
small synthetic, forced-treatment diagnostic; it does not establish a natural
shade distribution, gauge readability, or detector benefit. Earlier observations
of candidate blur concern the common appearance stack and are not isolated by this
control. The existing 48-image gallery keeps native image files and per-image
metadata; its `band` label corresponds to the raw `baseline` variant.
