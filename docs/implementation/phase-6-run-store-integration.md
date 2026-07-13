# Phase 6: SQLite run-store integration

## Goal

Connect the reviewed SQLite RunStore to normal chat sessions so new runs gain
append-only, restart-readable audit state while the legacy session JSON remains
the compatibility source during migration.

## Task 6

- Construct one RunStore per SessionStore using the configured runs directory.
- Create or ensure a corresponding SQLite run whenever a ChatSession is created
  or loaded from legacy session JSON.
- Mirror each SessionStore event to the run store after the legacy event is
  durably appended; mirror the current serialized session as the run snapshot.
- Mirror artifact records after successful session save so a restarted run-store
  exposes the current artifact values.
- If SQLite mirroring fails, do not erase or roll back the legacy session JSON;
  surface a clear runtime event/error instead of silently claiming the audit was
  stored.
- Do not alter public ChatSession fields, existing session JSON format, or
  existing CLI commands.

## Tests

1. Creating and saving a normal session creates a readable SQLite run snapshot.
2. User/tool events have the same order in legacy events and SQLite events.
3. Current artifact records are available after reopening the run store.
4. A simulated run-store failure leaves legacy session JSON readable and reports
   the mirror failure without recursively attempting to mirror that report.
5. Existing acceptance tests keep their legacy behavior.

## Constraints

- Reuse the reviewed RunStore and SessionStore only; no background worker,
  migration framework, API route, frontend, or dependency addition.
- Keep mirroring synchronous for this single-user phase so ordering is auditable.
- Redact model API keys only when a later caller supplies a redaction list; do
  not invent a second secret configuration path in this task.

## Review evidence

Write `docs/implementation/phase-6-run-store-integration-report.md` with
touched files, behavior, exact tests, compatibility notes, and concerns.
