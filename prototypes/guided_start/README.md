# PROTOTYPE: guided `start` session

Question: can one essentials-first session state machine support composer discovery, advanced editing,
preflight warnings, mandatory confirmation, pause/continue/stop, and post-run actions without
duplicating the existing atomic commands?

This is a retained throwaway prototype. It uses only in-memory fake data and never creates a composer,
pool, receipt, or output directory.

Run it from this worktree:

```powershell
uv run python prototypes/guided_start/cli.py
```

Use `--demo` to print a complete scripted journey without prompts.
