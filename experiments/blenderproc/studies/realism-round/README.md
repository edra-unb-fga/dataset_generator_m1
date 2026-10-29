# Bounded L4 realism screen

This saved design compares a sun-lit baseline with an exploratory overcast, rougher pad and
procedural environmental shadow treatment. Development has 20 distinct camera/seed intents,
paired across the two treatments; it also includes a small wall probe, contact/stacking
diagnostics and two 1280-pixel views. Reserved has 12 different seeds and repeats only the
paired treatments. Shared source pools, artwork and textures mean these are independent
**synthetic combinations**, not independent real-world scenes. The bundle's first three ground
materials and first HDR environment are used. The reference pool should contain varied positive
scenes; if it is smaller than the number of intents, source scenes repeat and this must be reported.
The fixed candidate is a screen, not evidence it improves realism. Tune only development; freeze
before reviewing or running reserved. Edit and preserve an explicit revised matrix before freezing
if development evidence warrants it; do not revise it in response to reserved results.

On the local machine, prepare a portable input from an existing, valid pilot configuration. The
bundle captures the current source and inputs, so rebuild after changing source:

```sh
uv run python scripts/blenderproc_pilot.py bundle --config /absolute/path/pilot.json --output-file /absolute/path/input.tar.gz
python experiments/blenderproc/studies/realism-round/supervisor.py run --phase development --bundle /absolute/path/input.tar.gz --output /absolute/path/realism-results --session UNIQUE-DEVELOPMENT-SESSION
# Independently inspect development and save review findings in /absolute/path/review.md.
python experiments/blenderproc/studies/realism-round/supervisor.py freeze --output /absolute/path/realism-results --review /absolute/path/review.md --bundle /absolute/path/input.tar.gz
python experiments/blenderproc/studies/realism-round/supervisor.py run --phase reserved --bundle /absolute/path/input.tar.gz --output /absolute/path/realism-results --session UNIQUE-RESERVED-SESSION
```

Run the `run` commands in detached, logged local processes if the controlling agent may stop.
The supervisor uploads only explicit inputs, retrieves and verifies an archive on completion or
error, then stops its named session. The remote runner measures fresh host and single-NVIDIA GPU
guards and packages each completed cell at a between-cell barrier. Guard aborts are failures;
never lower thresholds to retry. Results and downloadable cell archives are inside the verified
`results.tar.gz`, and matrices, budget, policy, measurements and logs remain in the evidence.
Do not run concurrent allocations for these phases. The persistent ledger reserves 45 minutes
per phase against a combined 90-minute maximum, including bootstrap, upload, rendering and
retrieval, even for faster runs. The remote phase targets 30 and 20 minutes respectively; setup
and retrieval contribute to the 60-minute soft target. Failed attempts consume their conservative
reservation; investigate and reconcile rather than silently resetting the ledger. The freeze records
hashes of the verified development archive, original bundle and bootstrap, review and reserved matrix.
A failed development phase can be frozen only for the documented 640/1280 broadcasting error after
all declared scenes, file hashes and sealed identities have been checked; the freeze retains the
original failure. The freeze does not judge
whether the review is adequate.

The watchdog attempts to stop at the reserved deadline; a host shutdown, failed network, stuck stop
request or expired credentials can defeat both retrieval and release. Therefore this is a best-effort
operational ceiling, not a guarantee of billable allocation time. A phase whose release cannot be
confirmed requires an external session check before another launch. Outputs under `/content` are
ephemeral until retrieved locally; per-cell archives help salvage a partial run while it remains
reachable. Sessions are billed even while waiting for the local review, which is why development
is stopped before reserved starts. Avoid placing credentials in bundles or reports.

After extracting a retrieved `results.tar.gz`, build a self-contained report with
`uv run python scripts/report_realism_round.py --input /path/to/extracted/results --output /path/to/report.html`.
The report embeds reduced review images; use the retrieved original PNGs for detailed inspection.
