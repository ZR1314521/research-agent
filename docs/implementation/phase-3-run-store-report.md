# Phase 3 SQLite run store report

## Touched files

- `research_agent/run_store.py`
- `tests/test_run_store.py`
- `docs/implementation/phase-3-run-store-report.md`

## Behavior delivered

`RunStore` is a small, standard-library-only SQLite persistence module for
new runtime state. It receives the configured `AgentConfig.runs_dir` from a
future caller and creates `run_store.sqlite3` directly inside that directory.
It does not import, alter, or read `SessionStore`, `ChatSession`, or existing
`runs/sessions/*` JSON/JSONL files.

- SQLite foreign keys are enabled for the store connection. The store requests
  WAL journal mode and continues with SQLite transactions if the filesystem
  does not support WAL.
- Runs retain creation metadata. Events are append-only and have a `(run_id,
  sequence)` primary key. Each append obtains its next sequence while holding
  a `BEGIN IMMEDIATE` write transaction, so sequences increase strictly within
  a run.
- Event and snapshot payloads are normalized through JSON serialization. Every
  supplied redaction value is replaced recursively in payload strings and
  object keys before either record is serialized and saved.
- Artifacts have one current value per `(run_id, name)` and are replaced with a
  SQLite upsert. Snapshots have one current value per run.
- `append_event(..., snapshot=...)` inserts the event and replaces the snapshot
  in the same transaction. A failed transaction rolls back both writes, so a
  snapshot cannot describe an event that was only partially persisted.
- `load_run()` reconstructs the run, ordered events, current artifacts, and
  current snapshot after reopening the database.

No AgentLoop, HTTP, dependency, configuration, or legacy session changes were
made in this phase.

## Tests

Focused coverage in `tests/test_run_store.py` verifies:

- database creation under a supplied runs directory and reopen recovery;
- strict event sequence ordering within one run, including an append after a
  fresh store connection;
- recursive caller-supplied secret redaction before event and snapshot
  persistence, verified by reopening and querying the raw SQLite JSON;
- artifact replacement retaining only the current named artifact;
- recovery of the latest snapshot and its associated event sequence after a
  fresh store connection; and
- transactional rollback when snapshot replacement is forced to fail, proving
  that its accompanying event is not persisted alone.

Exact command run:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_run_store -v
```

Exact result: `Ran 6 tests in 0.080s ... OK`.

## Remaining concern

The isolated store is intentionally not yet connected to AgentLoop or the HTTP
app; the next integration phase must decide which runtime transitions supply
snapshots and which caller-owned secret values belong in each redaction list.

## Review hardening

Snapshot payloads passed through `append_event(..., snapshot=..., redactions=...)`
now use the same recursive caller-supplied redaction before serialization as
event payloads. `replace_snapshot()` also accepts the optional `redactions`
keyword for standalone snapshot replacement.

The focused tests reopen and query the SQLite database directly to prove a
supplied secret is absent from both `events.payload_json` and
`snapshots.payload_json`. They also append a fourth event after reopening to
verify per-run sequences remain monotonic across connections, and inject a
snapshot upsert failure to prove the enclosing transaction rolls back its
event.

Exact focused command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_run_store -v
```

Exact result: `Ran 6 tests in 0.080s ... OK`.
