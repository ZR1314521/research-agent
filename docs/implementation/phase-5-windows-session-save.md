# Phase 5: Windows session persistence hardening

## Evidence

The full suite intermittently failed in `SessionStore.save()` with
`PermissionError [WinError 5]` during `session.json.tmp -> session.json`.
Rerunning the exact affected acceptance test immediately passed, which supports
a transient file-lock hypothesis rather than a deterministic data failure.

## Task 5

Harden the existing atomic session-save boundary without changing its public
semantics.

- Retain temp-file plus `os.replace`/`Path.replace` atomic replacement.
- Retry only `PermissionError` from the replacement a small fixed number of
  times with a short bounded backoff; do not retry malformed JSON, missing
  directories, or unrelated filesystem errors.
- If every retry fails, raise the original failure and leave the old session
  file intact.
- Add one focused test simulating a transient replacement lock that succeeds,
  and one test proving a persistent lock still raises.
- Existing session load/reset behavior must remain unchanged.

## Constraints

- Standard library only; no polling thread, global lock, or silent non-atomic
  fallback.
- The retry belongs in `SessionStore.save()`, the common root path, not in
  individual callers.

## Review evidence

Write `docs/implementation/phase-5-windows-session-save-report.md` with the
root-cause evidence, touched files, exact tests, and remaining concerns.
