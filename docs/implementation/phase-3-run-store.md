# Phase 3: SQLite run store foundation

## Goal

Introduce an append-only SQLite-backed run store for new runtime state without
modifying or deleting legacy `runs/sessions/*` data. This is the persistence
foundation for restart recovery and a future browser timeline.

## Task 3

Add a small, standard-library-only store module and focused tests.

Required behavior:

- New database is created under the configured runs directory and uses SQLite
  with foreign keys enabled and WAL mode when supported.
- It persists a run, append-only events, artifacts, and one current snapshot.
- Events have a strictly increasing sequence number within a run; event payloads
  are JSON and do not contain secrets supplied by the caller's redaction list.
- A restarted store can load the latest snapshot, events, and artifacts for a
  given run.
- Event append and snapshot replacement are atomic enough that a partial event
  cannot appear as completed after an interrupted write.
- Existing SessionStore and existing session JSON files are untouched.
- Add tests for create/reopen, monotonic event ordering, redaction, artifact
  replacement, and snapshot recovery.

## Constraints

- Use `sqlite3` from the standard library only; do not add an ORM or migration
  framework.
- Keep the public API small and typed. Do not wire the new store into AgentLoop
  or the HTTP app in this phase.
- Do not create user authentication, file permissions, or a frontend here.

## Review evidence

The implementer writes `docs/implementation/phase-3-run-store-report.md` with
touched files, behavior, tests, and remaining concerns. The reviewer inspects
those named files directly because this repository has no initial Git commit.
