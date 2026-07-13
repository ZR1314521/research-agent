# Phase 7 local workbench report

## Delivered

- `requirements-local.txt` records the local API requirements, including installed `python-multipart==0.0.32`; `workbench/package.json` records the React workbench requirements without installing them.
- `research_agent.app` binds launcher guidance to `127.0.0.1`, uses two explicit local CORS origins, and provides health, run creation/resume, message submission, SSE events, and standard FastAPI multipart upload routes.
- `workbench/` contains a minimal React source workbench for creating/resuming a run, sending messages, selecting/uploading files for the current run, and showing the refreshed latest reply, events, and artifact paths.
- `start_workbench.ps1` is the single startup command. It invokes `C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m uvicorn ... --host 127.0.0.1`, never changes `PATH`, and fails before launch when an offline frontend prerequisite is absent.

## Installed-tool evidence

```text
python=C:\Users\Z18803231258\AppData\Local\Python\pythoncore-3.14-64\python.exe
fastapi=0.139.0
uvicorn=0.51.0
python-multipart=0.0.32
httpx=0.28.1
app_factory=True
node=v24.14.1
npm=11.11.0
create-react-app=C:\Users\Z18803231258\AppData\Roaming\npm\create-react-app.ps1
```

## Verification

```powershell
C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m unittest tests.test_local_workbench tests.test_workbench_startup
# Ran 4 tests in 0.334s — OK

C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m unittest discover -s tests
# Ran 78 tests in 6.623s — OK

node -e "JSON.parse(require('fs').readFileSync('workbench/package.json', 'utf8')); console.log('workbench package metadata: valid JSON')"
# workbench package metadata: valid JSON

powershell -ExecutionPolicy Bypass -File .\start_workbench.ps1 -DryRun
# shows: ... -m uvicorn research_agent.app:app --host 127.0.0.1 --port 8877
# and: npm --prefix ...\workbench start
```

The React build/test was not run because `workbench\node_modules\.bin\react-scripts.cmd` is absent. Per the no-install/no-network constraint, no `npm install`, `npx`, or registry request was attempted. A normal launcher invocation exits before starting either process with that exact missing-artifact path.

## Startup

```powershell
.\start_workbench.ps1
```

When the local `react-scripts.cmd` artifact is supplied offline, this starts the API on `127.0.0.1:8877` and the React workbench via `npm --prefix workbench start`.

## Review fixes (2026-07-12)

- Replaced raw `Request.body()` upload handling and query-string filenames with `files: list[UploadFile] = File(...)` on both run and session upload aliases.
- The workbench now submits browser `FormData` from a multiple-file picker, registers the selected files for the active run, then applies the API response to refresh artifacts and events.
- Added `python-multipart==0.0.32` to local dependency metadata and FastAPI `TestClient` multipart coverage that proves original filename and bytes are preserved. Localhost-only bind guidance and the two explicit CORS origins remain unchanged.

## Verification after review fixes

```powershell
C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m unittest tests.test_local_workbench tests.test_workbench_startup
# Ran 4 tests in 0.416s - OK

node -e "JSON.parse(require('fs').readFileSync('workbench/package.json', 'utf8')); console.log('workbench package metadata: valid JSON')"
# workbench package metadata: valid JSON

C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m unittest discover -s tests
# Ran 78 tests in 7.244s - OK
```

The targeted and full Python runs emitted an existing FastAPI/Starlette `TestClient` deprecation warning for the installed `httpx` integration; they passed without failures. The full run also emitted an existing temporary HTTP 429 cleanup `ResourceWarning` while passing.

## Final review fixes (2026-07-12)

- Multipart upload responses now include the same sequenced event and artifact snapshot as `GET /runs/{run_id}`. The workbench replaces its view with that authoritative snapshot instead of clearing events, reconnects SSE from its last sequence whenever a run is refreshed, and ignores an already-seen SSE sequence.
- README now documents `POST /runs/{run_id}/files` as `multipart/form-data` with one or more `files` parts; obsolete raw-body/query-filename guidance was removed.

```powershell
C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m unittest tests.test_local_workbench tests.test_workbench_startup
# Ran 6 tests in 0.498s - OK

node -e "... validate workbench package metadata and upload/SSE source ..."
# workbench metadata and upload/SSE source: valid

C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe -m unittest discover -s tests
# Ran 80 tests in 7.860s - OK
```
