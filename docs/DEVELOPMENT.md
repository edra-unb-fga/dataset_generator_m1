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
- Guided-start/display change: run `tests/test_guided_start.py`, run-control and telemetry contracts; verify non-TTY refusal and one saved-composer journey.
- Generation/control change: run `tests/test_run_control.py`, `tests/test_generation_pool_contract.py`, `tests/test_preparation_inspection.py`, and telemetry contracts; exercise an external stop followed by resume and inspect the resulting pool.
- Geometry/annotation change: run scene, imaging, annotation-evidence, QA, inspection, and export contracts.
- Pool mask-evidence change: run annotation-evidence, generation-pool, inspection, scene, and export contracts; compare serial/process mask hashes and inspect both maintained families.
- Segmentation-export change: exercise detection and segmentation for random, stratified, and asset-disjoint splits; review fidelity warnings and both family QA galleries.
- Split-planning change: exercise impossible/fragile component fixtures, analyze-only no-write behavior,
  embedded analysis equality, deterministic assignments, and both detection/segmentation export paths.
- Appearance change: run filter tests, paired invariant tests, and inspect representative images.
- Experiment/report change: validate JSON/HTML consistency and every local artifact link.
- Placement-diagnostics change: compare geometry/annotation signatures before and after instrumentation,
  bound serialized record size, and run the production-path placement study.
- Performance claim: use paired fixtures in one environment and disclose sample size and warmups.
