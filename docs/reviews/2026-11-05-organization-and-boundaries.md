# Organization and behavior-boundary review

Status: local review for the coherent-scene work, 2026-11-05. This is a bounded
investigation, not a complete code audit, approval of any default, or instruction
to delete artifacts. Findings distinguish observations from hypotheses and
recommended decisions. The exact PR head, local changes and checks may change.

## What was examined

- Traced the 16 MiB swap stop from the retained aborted run through the shared
  monitor, study policy parsers, BlenderProc catalog and ordinary 2D paths.
- Compared the active worktree, `main`, draft PR #89 and its GitHub checks;
  inspected the user-facing candidate profiles, guided selection, experiment
  index, current study reports, resource policies and roadmap.
- Compared original plans and previous discussion against current findings,
  including motion severity, foreground wear, automatic hardware selection,
  evidence retention and per-family default approval.
- Measured broad local footprint and identified repeated study scaffolding. This
  was an inventory, not an instruction to remove any worktree or output.

No exhaustive call-graph, visual or security review was performed. No realistic
memory-exhaustion or destructive test was run. This document records the state
seen during the review, rather than claiming that no other problem exists.

## Prioritize before the current PR is merged

### 1. Name the actual deliverable and decision

Draft [PR #89](https://github.com/edra-unb-fga/dataset_generator_m1/pull/89)
is on `codex/coherent-scene-review`, head `72fb48b`, based on `main`. It is a
consolidation and opt-in candidate PR: 132 files and about 10,000 added lines in
the observed diff, including executable changes, schemas, multiple study drivers,
two large sample configs and evidence notes. Its breadth makes an explicit map of
production code, durable procedures, historical snapshots and deferred prototypes
important for review. A clean merge status is not a code-quality verdict.

The actively inspected worktree is `codex/coherent-scene-defaults`, based on
`6a1391e`, with both modified and untracked work. Some changes overlap the PR;
the new [domain-adaptation screen](../experiments/domain-adaptation-v1/README.md),
foreground comparison notes, and the local swap-warning change are outside the
observed PR head. The PR worktree was clean. Verify the actual diff and copy or
commit only deliberate changes when consolidating; never assume a local file is
already in the PR. Preserve source identities and avoid overwriting either tree.

**Suggested action:** make a short review table for each intended PR component:
shipped/opt-in/experiment, current source revision, evidence and owner, and
whether it is actually in the PR. Decide whether the later capture study is a
separate follow-up. Preserve the separate per-family and 3D default decisions;
merging selectable candidates does not itself approve a default. A user can
approve a useful provisional default without waiting for real-world data, as
long as it is labeled uncalibrated and the known limitations are accepted.

### 2. Reconcile benchmark guards with run intent

The [monitor](../../src/dataset_generator_m1/blender_runner.py) samples
system-wide cumulative swap writes since launch. Historically it stops when
those writes exceed the configured threshold. The stopped local source study
observed 18,862,080 bytes of new system-wide swap writes against a 16 MiB
threshold, while peak process-tree RSS was 261,910,528 bytes and minimum system
available memory was 7,246,331,904 bytes. This does not identify the process
that caused swapping or show an imminent out-of-memory event. A fixed cumulative
limit also makes duration relevant: a long run can eventually cross it without
sustained thrashing.

Scope correction: this monitor is used by the optional BlenderProc coordinator
and multiple guarded study wrappers. The ordinary 2D generator paths inspected
do not call this monitor, so the evidence does **not** show that every normal 2D
generation run has the 16 MiB stop. Other 2D memory estimates, preflight behavior
and controls are separate and deserve their own trace if changed.

The earlier local change added a warning action to the shared monitor and to the
`guarded_effect_combinations.py` policy parser. Only the new
`experiments/domain-adaptation-v1/local-warning-policy.json` selects it. It is
uncommitted and is not a project-wide fix. The separately duplicated
`guarded_foreground_context.py` parser and BlenderProc's strict
`blender_execution.Guards` schema do not expose the warning field; their
existing policies continue to abort. The default
`experiments/blenderproc/execution/profiles.json` also has a fixed 10 GiB **host
summed-RSS** cap, not a 10 GiB GPU VRAM cap. Adaptive setup is available, but
the fixed fallback remains a separate behavior.

The study README's instruction not to weaken a guard automatically after a stop
protected comparable runs; it should not be generalized into a ban on reviewing
an inappropriate policy after new evidence or an explicit user decision.

**Suggested action:** before merging a PR that includes the warning change,
scope it explicitly, document which paths accept which policy and add behavioral
tests for warn versus stop, unavailable telemetry and independent memory floors.
For broader use, separately decide benchmark-validity warnings versus real
resource protection, including swap rates/pressure, per-process or container
limits where available, and user-facing settings. Do not remove memory safety
guards indiscriminately; sampled guards cannot guarantee protection against an
OOM between samples. If the policy change is excluded from this PR, document it
as a separate pending change rather than claiming it shipped.

### 3. Make profiles and default promotion legible

The current `coherent-varied` profiles use 65% sampled foreground wear and 15%
foreground grain. Their image-space motion blur is 20% at 3–5 pixels for the
general profile and 5% at 3 pixels for the manometro variant. The later
adaptation screen used different provisional blur weights (70% pad/landing and
60% gauge, including a 15-pixel tail) in a standalone experiment. None of those
study weights is an approved production setting, and sampled activation is not
the same as a visibly meaningful effect. The latest user preference favors more
frequent motion blur and retains severe gauge cases; that preference should be
reconciled with the earlier reduced-motion profile rather than silently lost.

The guided `coherent` action chooses the manometro-specific candidate only when
the composer family reference exactly equals `builtin:family/manometro`; an
equivalent externally referenced family would fall through to the general
profile. Determine whether supporting equivalent external family references is
in scope, and test/document the outcome instead of assuming it is resolved.
Existing inline overrides deliberately remain active and should be visible in
the final resolved configuration.

**Suggested action:** a one-page selection table should identify, for each
family, current legacy/default behavior, selected candidate, independent
appearance/scene choices, intended behavior on old composers that omit an
appearance, prominent probabilities, override precedence and evidence. Test
explicit legacy profiles and omission before promoting anything. Family-specific
approval applies to defaults, not to retaining useful opt-in variations.

### 4. Complete the checks required for the actual diff

At inspection, PR #89's Python 3.13 and 3.14 test jobs succeeded, while the
`journey` check was skipped. The development guide calls for `ci:full` when
generation, configuration, telemetry or related contracts can change; this PR
contains such changes. Check why that job is skipped and run the relevant full
journey and required schema/compatibility checks against the **final PR head**.
Earlier local tests or tests of an uncommitted worktree are not proof for that
head. Record incomplete platform checks without making unrelated Windows work a
blocking requirement contrary to the user's Linux/Docker preference.

Before default promotion, check resolved preset identities and old omitted and
explicit composer behavior, generated schema, representative serial/parallel
annotation invariants, and user-facing profile selection. Treat visual evidence
and throughput as decision evidence, not pass/fail proof of model performance.
As a bounded local diagnostic, `test_coherent_candidate.py`,
`test_directional_shade.py` and `test_scene_presets.py` passed 46 tests against
the modified worktree, with one expected unrestricted-ground warning. This is not
a substitute for verification of the final PR commit.

### 5. Be honest about the review evidence

The [2D screen](../experiments/coherent-scene-studies-v1/2026-11-05-2d-screen.md)
reports valid paired geometry/masks but varying multiple effects at once. Its
fresh manometro sample activated the reduced motion blur in 0/20 cases. The
[3D screen](../experiments/coherent-scene-studies-v1/2026-11-05-3d-screen.md)
reports that a revised natural draw did not exercise the conditional fill and
contained no revised indoor-broad sample. These are coverage gaps, not failures
of the entire work or reasons to prevent a user making a provisional choice.

The [domain screen](../experiments/domain-adaptation-v1/README.md) uses 12 prior
2D JPEG images and four existing 3D renders. Its variants are forced, sampled
mixtures are small, references are development backgrounds, and raw images and
archives live under ignored local outputs. 3D is RGB postprocessing, not new
physical renders. Source masks were untouched, but those postprocessed images
were not exported as newly validated annotation pools. Its reproduction command
regenerates the 812 core cards; the combined 860-card report also adds 48 older
surface cards by a separate step. Make a durable, reproducible review bundle and
record dependencies before treating the gallery itself as portable.

### 6. Clarify L4 selection

The 6-worker × 2-thread 640px recommendation is in the explicit
`colab-l4-camera-study` screen profile, selected through
`prepare_blenderproc_run.py --screen-profile`; larger frames use 4 × 1. It is
not an automatically selected L4-specific rule in the ordinary execution
catalog. The main catalog has a generic GPU fallback. The README says this, but
the earlier goal of hardware-appropriate automatic choices can easily be
misunderstood. Decide whether explicit selection is sufficient for this PR; if
not, design capability-based automatic selection and fallback separately with
clear evidence and user override. Do not portray the experimental screen as a
universal optimal configuration.

### 7. Correct a concrete stale navigation cue

The [product command list](../SPEC.md) shows `configure --family
landing|manometro`, and the [development guide](../DEVELOPMENT.md) still says to
inspect “both maintained families” for mask changes. The executable family
catalog returned `landing-pad`, `landing` and `manometro` during this review.
These examples can mislead a reviewer into omitting the rectangular family.
Update the task guidance and relevant checks to include all three as a small
documentation correction in the appropriate PR; no product behavior change is
needed. Other occurrences have not been exhaustively audited.

## Document for deeper review after the PR

1. **Study/runtime seams.** Study scripts import `monitor` from a Blender-named
   production module; two wrappers have separate guard models and resolution
   logic. A shared policy/telemetry seam could reduce accidental divergence, but
   a refactor must preserve old study identities and explicit policies. Review
   also process-tree summed RSS versus shared memory, cgroup-aware limits, slow
   sampling and GPU device selection. These are hypotheses to investigate, not
   claims of an observed failure in every environment.
2. **Study scaffolding and provenance.** The `ground-mapping-followup` and
   `paired-lighting` supervisors are byte-identical; nearby study supervisors
   are similar. Some duplication may intentionally freeze historical sources.
   Distinguish reusable controllers from immutable historical drivers before
   deduplicating. Extract only when tests preserve artifact and shutdown
   semantics; never silently replace historical snapshots with current code.
3. **Navigation and retained outputs.** This worktree currently has roughly
   33 MiB under `docs/experiments`, 33 study README files, and about 3.0 GiB
   across 57 local experiment output directories. These sizes are observations,
   not proof of waste. Many worktrees also exist and may contain unique ignored
   evidence. Inventory each item's purpose, source fingerprint, recoverability,
   owner and archival location before any cleanup. Use the existing retention
   guide; do not automatically delete or commit raw pools.
4. **Evidence and UI discoverability.** The study index is helpful, but long
   chronological reports, experimental profile names and local-only galleries
   still make it hard to answer “what ships, what should I use and why?” Add
   concise stable task-oriented entry points, link exact current verdicts, and
   retain historical records behind them. Do not reclassify historical evidence
   as current or merge visual preference with detector evidence.
5. **Configuration boundaries.** Audit scene/appearance presets, guided setup,
   explicit versus implicit defaults, hardware execution settings, and resolved
   provenance together. Decide how profile presets combine with inline overrides
   and how a family-specific default is chosen. Keep optical effects distinct
   from foreground material and scene illumination. Geometry-changing effects
   require a different annotation contract from RGB-only effects.
6. **Shared engine contract and placement.** Preserve alpha coverage versus 3D
   binary masks in [#84](https://github.com/edra-unb-fga/dataset_generator_m1/issues/84).
   Keep requested-count fulfillment [#29](https://github.com/edra-unb-fga/dataset_generator_m1/issues/29),
   background QA [#27](https://github.com/edra-unb-fga/dataset_generator_m1/issues/27),
   and nested placement [#31](https://github.com/edra-unb-fga/dataset_generator_m1/issues/31)
   visible rather than letting them disappear into a broad realism cleanup.
7. **Real-world evidence.** Calibration, external predictions and matched
   2D/3D evaluation remain under #59, #61 and #64. They are important later
   evidence, not a requirement to postpone all provisional engineering defaults.

## How to find and prevent similar boundary mistakes

For each proposed policy, trace **intent → configuration → call sites → behavior
→ user-visible message → evidence → documentation**. List the intended
consumers and the consumers actually sharing it. Ask whether the condition is a
hard correctness failure, a resource safety stop, a benchmark-validity warning,
or an uncalibrated preference; document its scope and a concrete example of
expected and unexpected activation. Test the relevant caller and a neighboring
caller that should remain unaffected. Compare the final PR head with the working
tree and main, not just a conversation summary or a previous run.

Use explicit ownership and lifecycle labels for product code, optional backends,
reusable study infrastructure, frozen historical drivers, disposable prototypes
and local raw data. At handoff record which assumptions were reviewed, which are
still hypotheses, how to reproduce or locate the evidence, and the smallest next
decision. Keep this lightweight: add checks for demonstrated boundary risks,
not blanket approval gates or a large mandatory review checklist.
