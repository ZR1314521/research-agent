# Phase 8 workbench verification report

## Status

The local launcher was updated without changing Agent or document-summary
behavior. The frontend production build, non-interactive frontend test command,
targeted API/startup tests, and full Python regression pass. The launcher keeps
both documented loopback ports and dry-run output, starts each background
process in a hidden window, reports the two process IDs it created, and cleans
up either captured process if a later launcher step fails.

The API portion of the live localhost smoke check returned HTTP 200. Full
frontend HTTP verification and PID-tree cleanup could not be completed because
this environment denied `taskkill` access to the launcher-created PIDs; the
required elevated, self-contained verification run was then rejected by the
environment due to its usage limit. A final read-only check found no listeners
on ports 8877 or 3000.

## Touched files

- `start_workbench.ps1`
- `docs/implementation/phase-8-workbench-verification-report.md`

## Launcher changes

- `Start-Process` now uses `-WindowStyle Hidden -PassThru` for the API and
  frontend processes.
- The frontend detached process uses the executable `npm.cmd` shim. In this
  Windows session, `Get-Command npm` resolves to `D:\nodejs\npm.ps1`, which
  cannot be started detached (`Access is denied`), while `D:\nodejs\npm.cmd`
  is the installed executable shim.
- Launcher output includes `[api pid]` and `[workbench pid]`. Its failure path
  stops only captured PIDs that it started.

## Verification evidence

```powershell
npm --prefix workbench run build
# Exit 0. Compiled successfully.
# build/static/js/main.aa89033a.js: 46.94 kB gzip
# build/static/css/main.0d93f69a.css: 333 B gzip
```

```powershell
npm --prefix workbench test -- --watchAll=false --passWithNoTests
# Exit 1 before test discovery: Error: spawn EPERM in jest-worker.

npm --prefix workbench test -- --watchAll=false --runInBand --passWithNoTests
# Exit 0. No tests found, exiting with code 0.
```

`--runInBand` is a verification-only Jest invocation that avoids the Windows
worker-process permission failure; no frontend source or package metadata was
changed.

```powershell
& "$env:LOCALAPPDATA\Python\bin\python.exe" -m unittest tests.test_local_workbench tests.test_workbench_startup
# Exit 0. Ran 6 tests in 0.552s - OK.

& "$env:LOCALAPPDATA\Python\bin\python.exe" -m unittest discover -s tests
# Exit 0. Ran 80 tests in 11.824s - OK.
```

Both Python commands emitted pre-existing warnings from the installed
FastAPI/Starlette TestClient integration and temporary HTTP 429 cleanup; they
did not cause test failures.

```powershell
powershell -ExecutionPolicy Bypass -File .\start_workbench.ps1 -DryRun
# Exit 0.
# [api] ... -m uvicorn research_agent.app:app --host 127.0.0.1 --port 8877
# [workbench] npm --prefix ...\workbench start
```

Live smoke sequence:

```powershell
# Preflight: no listeners on 127.0.0.1:8877 or :3000.
powershell -ExecutionPolicy Bypass -File .\start_workbench.ps1
# Exit 0; emitted launcher-created API and workbench PIDs.

Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8877/health
# HTTP 200: {"status":"ok","bind_host":"127.0.0.1","public_network":false,...}
```

The subsequent frontend request to `http://127.0.0.1:3000/` could not connect
within this sandbox. Cleanup using only the two launcher-emitted PIDs was
denied (`taskkill`: `Access is denied`); the elevated self-contained retry was
rejected by the environment before execution. A later read-only check reported
`No listeners remain on 127.0.0.1:8877 or :3000.`

## Startup

```powershell
.\start_workbench.ps1
```

This starts the API at `http://127.0.0.1:8877` and the React development server
on its local default port. Use the following command to inspect the two
loopback launch commands without starting either process:

```powershell
.\start_workbench.ps1 -DryRun
```
