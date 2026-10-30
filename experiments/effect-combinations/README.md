# Paired 2D effects comparison

This study freezes nine named treatments and reuses scene intents across them. Wear,
shared lighting, shade, and local context adaptation each have an isolated cell;
wear plus lighting, wear plus context, and all effects together expose interactions.
Enabled effects are forced on in the isolated and all-effects controls to make their
impact visible, while strength is sampled. `all-capture` uses sampled lighting,
shade, and context probabilities and the modest camera preset. The baseline and
other controls disable capture effects. All cells use premultiplied alpha resampling.

Each scene is checked for the same geometry, annotations and masks across cells.
The offline report shows the full frame, an identical crop of the largest target,
actual applied-effect traces, and mean absolute RGB change inside and outside visible
alpha support. Difference is an effect size, not a realism score. JPEG encoding,
mask boundaries and camera transforms can affect the outside-mask measurement;
compare visually and inspect traces. Synthetic images are not a test of detector
performance. Seeds and assets are not a real-image holdout.

To run on Colab, build a sealed bundle and start the supervisor in a detached process:

```sh
.venv/bin/python experiments/effect-combinations/build_colab_bundle.py \
  --output /absolute/output/bundle.tar.gz
nohup .venv/bin/python experiments/effect-combinations/colab_supervisor.py run \
  --bundle /absolute/output/bundle.tar.gz --output /absolute/output/run \
  --session unique-session-name --colab /home/david/.local/bin/colab \
  > /absolute/output/supervisor.log 2>&1 < /dev/null &
```

A recorded policy sets eight paired scenes, CPU workers, adaptive host memory and
swap guards, remote deadline and 25-minute allocation watchdog. The remote process
archives partial results in its `finally` block. The supervisor retrieves and verifies
the archive, then stops the runtime even after failure; the independent watchdog
provides a final stop attempt. One blocking `colab exec` waits for the study rather
than polling stable runtimes. Review `status.json`, `result-metadata.json`, and
`results.tar.gz`; the bundle and policy hashes are recorded. Do not weaken guards
automatically if a study is interrupted. Independently verify runtime shutdown.
