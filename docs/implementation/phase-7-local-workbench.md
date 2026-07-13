# Phase 7: local API and React workbench bootstrap

## Goal

Make the existing research agent usable through a localhost browser workbench
without downloading any new dependency. The user has installed FastAPI,
Uvicorn, and create-react-app globally; use module invocation rather than
modifying the system PATH.

## Task 7

- Add reproducible project dependency metadata that documents the existing
  Python/API and frontend requirements without installing packages.
- Harden the existing FastAPI app for localhost single-user use: bind guidance,
  health endpoint, run creation, message submission, SSE event endpoint, and
  file upload route must remain usable when FastAPI is installed.
- Add a minimal React workbench using already installed tooling only. It must
  support a message input, create/resume a run, display streamed/polled events,
  display the latest assistant message, and show a list of artifact paths.
- Provide a single project startup command that starts the API and opens/serves
  the React workbench without requiring users to edit PATH. It must fail with a
  clear dependency message if tools are not installed.
- The server must default to loopback only; no wildcard host, no API keys in
  frontend code, and no CORS wildcard.

## Tests

1. API app factory is importable with FastAPI present and health is loopback-safe.
2. Run/message/event response contracts are tested using FastAPI's test client
   or a direct compatible API test.
3. Startup script dry run shows module-based Uvicorn invocation and frontend
   command without launching a server.
4. Frontend build/test is run only if the existing installed React tooling can
   do so offline; otherwise record the exact missing artifact without download.

## Constraints

- Do not run npm/pip install, npx network fetches, or modify system PATH.
- Reuse existing `research_agent.app` and new SessionStore/RunStore integration.
- Keep scope to the operational bootstrap; do not implement approvals, shell,
  browser automation, or document UI in this task.

## Review evidence

Write `docs/implementation/phase-7-local-workbench-report.md` with installed
tool evidence, touched files, exact test/build commands, startup instructions,
and blockers.
