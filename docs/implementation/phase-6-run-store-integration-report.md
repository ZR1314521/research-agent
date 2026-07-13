# Phase 6 run-store integration report

## Touched files

- `research_agent/session.py`
- `tests/test_run_store_integration.py`
- `docs/implementation/phase-6-run-store-integration-report.md`

## Behavior

`SessionStore` owns one `RunStore` at its configured runs directory. Each new
or loaded `ChatSession` is represented by a run using its existing
`session_id`; no `ChatSession` field or legacy JSON field was added.

- A completed legacy session save is mirrored synchronously as the current
  SQLite snapshot, then its artifact records are upserted.
- A legacy `SessionStore.event()` first appends the JSONL event and saves the
  JSON session, then appends the same event and serialized session snapshot to
  SQLite. This keeps normal legacy and SQLite event order identical.
- If a SQLite write fails, the already-written legacy session is retained and a
  legacy-only `run_store_mirror_failed` event plus `metadata.run_store_mirror_error`
  reports the failure. The report is written through private legacy helpers, so
  it is never recursively mirrored.
- Existing JSON field names, CLI commands, APIs, tools, and dependencies remain
  unchanged.

## Tests

Focused integration command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_run_store_integration -v
```

Exact result: superseded by the review-fix verification below.

Full regression command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest discover -s tests -v
```

Exact result: superseded by the review-fix verification below.

## Compatibility and concern

Legacy `runs/sessions/<session_id>/session.json`, `execution_log.jsonl`, and
`workflow_trace.json` remain the compatibility source and are written before
SQLite mirroring. `RunStore` is kept open for the lifetime of its
`SessionStore`; `SessionStore.close()` is available for deterministic teardown.

## Review fixes and verification

- `SessionStore` now has an idempotent `close()`, context-manager support, and
  a safe best-effort finalizer. `ResearchChatAgent.close()` forwards to it, and
  `run_terminal()` closes the agent in `finally`.
- Test callers now close their owned stores before temporary directories are
  removed, eliminating the new SQLite connection warnings from the full suite.
- The event-order regression reads durable `execution_log.jsonl` records and
  compares their event sequence directly with reopened SQLite events.

Focused command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_run_store_integration -v
```

Exact result: `Ran 6 tests in 0.171s ... OK`.

Full regression command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest discover -s tests -v
```

Exact result: `Ran 73 tests in 6.840s ... OK`.

## P1 close-retry fix

`SessionStore.close()` now marks the store closed only after
`RunStore.close()` returns successfully. A close failure therefore remains
visible to the caller and a later `close()` retries the underlying store.

Focused command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_run_store_integration.RunStoreIntegrationTests.test_failed_close_remains_retryable -v
```

Exact result: `Ran 1 test in 0.012s ... OK`.

Full regression command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest discover -s tests -v
```

Exact result: `Ran 74 tests in 6.582s ... OK`.
