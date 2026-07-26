# Verdict

The summary cockpit is suitable for production with drill-down sections. Users could follow the
relationship between a profile choice, ETA/risk, receipt validity, and run state without learning the
resolver implementation.

Validated decisions:

- Keep one summary screen with subject drill-down.
- Treat receipts as derived state bound to the current composer revision.
- Model pause as `running -> draining -> paused` and continue as `paused -> running`.
- Keep profile selection and advanced effect construction in the same appearance section.
- Reject duplicate stable effect IDs/configurations in production; the prototype intentionally exposed
  how confusing silent duplication would be.

Only the state transitions and information hierarchy should be carried into production. The terminal
shell remains throwaway.
