# Standard execution

Uses one worker for predictable, portable behavior. Choose `auto` or a positive integer through a typed
override when local CPU and memory capacity are known. Worker count affects preflight receipts and runtime
provenance even though deterministic scene and effect streams remain stable.

Automatic mode uses one OpenCV thread per worker unless explicitly configured. It plans capacity,
not the fastest throughput. Use `execution candidates` and a guarded repeated benchmark followed by
`execution recommend` to save an explicit local choice; see `docs/EXECUTION_TUNING.md`.
