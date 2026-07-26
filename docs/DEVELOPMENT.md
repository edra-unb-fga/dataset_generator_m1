# Development Guide

## Start here

Install and validate the repository:

```powershell
uv sync --locked --extra dev
uv run python scripts/generate_schemas.py
git diff --exit-code -- docs/schema
uv run pytest -q
```

Read `CONTEXT.md` before changing domain terms and `docs/SPEC.md` before changing schemas, commands,
or artifacts. Update the closest documentation in the same pull request.

## Branches and worktrees

Use `codex/<topic>` branches. Use a separate Git worktree for prototypes or concurrent feature work.
A prototype answers one design question, records a verdict, and is not merged wholesale. Retain a
useful prototype branch when production work may reuse its pure logic or visual ideas.

## Pull requests

Keep PRs reviewable and record:

- intent and affected contracts;
- schema and output compatibility;
- deterministic tests;
- visual or performance evidence when pixels or cost change;
- documentation changes;
- whether generated artifacts are ignored or deliberately reviewed and tracked.

Fast CI runs on pull requests and pushes to `main`. The manual Windows workflow is a correctness and
artifact smoke test, not a machine-independent latency gate. Merge only after required checks pass.
Repository settings delete merged branches automatically; retained prototype branches are the
intentional exception.

## Minimum verification

- Schema/config change: regenerate schemas and run profile/CLI tests.
- Geometry/annotation change: run scene, imaging, and export contracts.
- Appearance change: run filter tests, paired invariant tests, and inspect representative images.
- Experiment/report change: validate JSON/HTML consistency and every local artifact link.
- Performance claim: use paired fixtures in one environment and disclose sample size and warmups.
