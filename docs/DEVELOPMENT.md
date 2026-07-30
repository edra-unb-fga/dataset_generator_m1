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

Fast CI runs the complete deterministic test suite on Python 3.13 and 3.14 for pull requests and
pushes to `main`. Python 3.14 additionally checks generated-schema drift and builds the package.
Superseded commits are cancelled.

Apply the `ci:full` label when a pull request can affect generation, assets, configuration resolution,
telemetry, QA, run control/resume, or packaging. That opt-in Ubuntu workflow exercises the public CLI
from catalog discovery through separate exports, generates 10 samples for each maintained family,
and verifies the compact pool evidence. It is also available through manual dispatch. Do not apply it
to documentation-only changes. The uploaded evidence expires after seven days and intentionally omits
the generated image and export directories.

The manual Windows workflow remains a platform-correctness and augmentation-study smoke test. Neither
full workflow is a machine-independent latency gate. Merge only after the checks required by the
affected contract pass.
Repository settings delete merged branches automatically; retained prototype branches are the
intentional exception.

## Minimum verification

- Schema/config change: regenerate schemas and run profile/CLI tests.
- Configurator/catalog change: run configurator, override, profile, CLI, and preflight contracts; confirm every executable effect has file-backed guidance.
- Generation/control change: run `tests/test_run_control.py`, `tests/test_generation_pool_contract.py`, `tests/test_preparation_inspection.py`, and telemetry contracts; exercise an external stop followed by resume and inspect the resulting pool.
- Geometry/annotation change: run scene, imaging, and export contracts.
- Appearance change: run filter tests, paired invariant tests, and inspect representative images.
- Experiment/report change: validate JSON/HTML consistency and every local artifact link.
- Performance claim: use paired fixtures in one environment and disclose sample size and warmups.
