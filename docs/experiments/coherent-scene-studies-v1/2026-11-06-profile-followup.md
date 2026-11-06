# Coherent profile follow-up: 2026-11-06

These are local 640×640 engineering comparisons, not real-camera calibration or
evidence of detector performance. The profiles remain opt-in until the separate
family and 3D default reviews. Exact raw pools and the gallery are ignored local
artifacts; keep their recorded drivers, policy, assets and source hashes together.

## Paired 2D screen

All five studies covered landing-pad, landing and manometro, with 4 matched slots
per family except the 8-slot fresh balanced/coherent comparison. The 144 full
images have paired scene geometry, annotations and full/visible mask signatures;
the gallery also contains largest-target crops. Studies compare balanced against
`realistic-heavy` and earlier coherent profiles, surface-varied and challenging
against earlier coherent, and a forced 15-pixel motion effect against an unblurred
capture with other effects sampled as before. Forced 15px is a diagnostic, not a
natural frequency estimate. Source assets are reused.

The fresh balanced draw happened to contain, out of eight per family: landing-pad
3/1/0/4, landing 3/1/0/4, manometro 1/1/0/6 for 3px/7px/15px/unblurred.
It did not exercise the severe tail; inspect the separately forced comparison.
The high blur can make fine gauge markings unreadable while other image context
remains. Stronger wear can still show repetitive stains; it is a variation for
review, not a new physical plastic texture. These observations are qualitative.

## Review recommendations, not approvals

- **Landing-pad:** start review with balanced capture and shared shade. Compare
  surface-varied against it at full size before deciding whether the extra marks
  should be part of an ordinary mixture.
- **Landing:** start from the same balanced capture choice, but separately inspect
  wear on the light circular artwork, where repeated marks are more conspicuous.
- **Manometro:** start with the gauge-specific balanced candidate and review the
  forced 15px examples at full size. The proposed 5% severe tail is an editable
  starting choice, not an established readability or detector threshold.
- **3D:** retain the reviewed balanced mixture and compare the broad/material
  candidate as a separate choice. The latter reweights existing component presets;
  its weights are not evidence that lighting artifacts have been resolved.

Challenging is useful as a selectable stress mixture; these small samples do not
justify making it the default. Each family and the 3D mixture need their own user
approval before promotion.

Single ordered, unwarmed four-pair comparisons against `realistic-heavy` measured
2.19→1.88 accepted images/s for landing-pad, 2.55→2.13 for landing, and 2.48→2.20
for manometro. They are small exploratory measurements, not stable performance
claims. Preparation time and unrelated system activity were not standardized.
Across the five studies, process-tree RSS peaked at about 340 MiB. The forced
study recorded 21.8 MiB of system-wide swap writes as a warning and completed;
this counter does not attribute the activity to the generator.

The local gallery `outputs/experiments/pr89-profile-review/` includes these
comparisons and 24 existing 3D renders before and after the selected RGB capture
profile. The latter are post-render treatments; geometric masks are copied
unchanged and are not blurred-optics annotations. They are not new 3D renders.

## Fresh 3D mixture

A fresh 12-scene L4 draw of the broader material candidate completed and passed
archive, source, image, mask and shutdown verification. It sampled six open, four
outdoor and two indoor scenes, reusing the same reference assets. Archive SHA-256:
`98471e9ead7004bf88e8988f2cd8ee97ff600388fae41e68588c9b3c816c0fa8`;
input bundle identity: `cc710515bb33883fabda37fbd0a4b4ba3d6833b8f58fe029ae6fcb62b60b3b15`.
The runtime took 134 seconds for its remote script, including setup, and was
shut down by its supervisor. These are fresh sampled scenes, not matched new
lighting renders or an estimate of artifact frequency.

On visual inspection, multiple targets remain recognizable and the sample includes
several ground appearances. The indoor examples 001 and 007 are pale, outdoor 008
is strongly washed out, and open 011 is dark with strong geometric shadows. Some
challenging cases are intentional, but the tiny and uneven context sample does not
establish whether they occur at a desirable rate. Earlier matched lighting triplets
are documented in [the 3D screen](2026-11-05-3d-screen.md); they investigate the
component lights, not the newly weighted distribution.

The preceding 24-scene attempt produced no retrievable results: its independent
watchdog stopped the runtime at its deadline after the execution connection failed
to complete. It is not counted as a study. Across both attempts the displayed
Colab balance fell from 154.90 to 154.58 CU, with zero active assignments after
shutdown. The observed 0.32 CU difference may lag actual billing; before allocation
the retry's conservative aggregate gate was 1.39 CU against the 2 CU limit.

## Reproduction

`experiments/foreground-context/coherent-study/run.py` accepts `--treatment`
`coherent-balanced`, `coherent-surface-varied`, or `coherent-challenging` and
`--baseline realistic-heavy|coherent-varied`. `motion_ablation.py --force-kernel
15` produces the forced comparison. Both accept an explicitly saved policy.
`scripts/postprocess_blender_capture.py` applies a profile's final effects to
verified BlenderProc scenes in a new directory. `scripts/collect_coherent_profile_review.py`
and `scripts/build_scene_review_gallery.py` build a portable image-first gallery
once all recorded source pools are available. Keep output pools and render archives
outside tracked source; document any absent source rather than fabricating it.
To include a recovered natural 3D run, pass its verified review directory with
`--natural-3d`; the collector checks its evidence and image hashes before copying
the images, and labels them as a fresh natural sample.
