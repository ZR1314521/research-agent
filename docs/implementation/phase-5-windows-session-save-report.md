# Phase 5: Windows session persistence hardening report

## Root-cause evidence

The observed failure was `PermissionError [WinError 5]` at the atomic
`session.json.tmp -> session.json` replacement in `SessionStore.save()`. The
affected acceptance test passed immediately on rerun, which is consistent with
a transient Windows file lock rather than malformed session data or a missing
directory. The retry is therefore limited to `PermissionError` raised by that
single replacement operation; JSON serialization, directory creation, and
workflow-trace writes retain their existing behavior.

## Change

`SessionStore.save()` keeps the temp-file-and-replace protocol and makes up to
three replacement attempts. It waits 10 ms then 20 ms after the first two
`PermissionError` failures. If all attempts fail, it re-raises the first
`PermissionError`; because replacement never succeeded, the existing
`session.json` is left intact. No non-`PermissionError` is retried.

## Touched files

- `research_agent/session.py`
- `tests/test_runtime_hardening.py`
- `docs/implementation/phase-5-windows-session-save-report.md`

## Tests

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_runtime_hardening -v
```

Result: `Ran 11 tests in 0.249s` / `OK`, including focused transient-lock and
persistent-lock coverage.

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

Result: Phase 5 tests passed, but the full suite ended with four unrelated
errors: three `ModuleNotFoundError: No module named 'docx'` failures in
`test_agent_core`, and one existing document-export acceptance failure
(`KeyError: 'docx_output'`). The environment confirms `docx = None`; no
dependency or document workflow was changed for this phase.

## Remaining concern

A lock lasting longer than the bounded 30 ms retry window still raises by
design; the caller retains the old session file and can retry later.
