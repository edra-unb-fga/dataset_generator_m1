# Run control

Generation pools expose a durable coordinator state in `control.json` and an append-only audit trail in
`control-events.jsonl`. These files belong to the pool and are safe to inspect from another terminal.

```powershell
uv run python -m dataset_generator_m1 run status outputs/my-run
uv run python -m dataset_generator_m1 run pause outputs/my-run
uv run python -m dataset_generator_m1 run continue outputs/my-run
uv run python -m dataset_generator_m1 run stop outputs/my-run
```

Interactive live/full displays also accept `p` to pause or continue and `s` to request a graceful stop.
`Ctrl+C` interrupts normally; a second interrupt during worker shutdown forces termination.

## State and checkpoint behavior

- `pause` changes the desired state immediately. The coordinator finishes its current sample or bounded
  process-worker batch, reports `draining`, checkpoints committed results, and then becomes `paused`.
- A paused coordinator stays alive but schedules no work. `continue` resumes that same process.
- `stop` drains bounded in-flight work, writes an `interrupted` summary, and exits with a resumable pool.
- `generate --resume` verifies the unchanged configuration and asset fingerprints and continues missing
  deterministic slots. It also repairs readable JSONL streams from their per-record atomic journals.
- Complete, interrupted, and failed runs reject further external control requests. An explicit resume may
  reopen a run for repair or remaining work.

Live throughput and ETA use active coordinator time only; paused time is reported separately. On resume,
the ETA window starts after historical records are replayed, so prior samples are not counted as newly
instantaneous work.

Quiet and JSON generation use the same state files but never read terminal keys. Control them from another
terminal with the `run` commands. The control record is atomically replaced and requests/transitions are
serialized; the event log records actor, sequence, desired state, actual state, and timestamps.
