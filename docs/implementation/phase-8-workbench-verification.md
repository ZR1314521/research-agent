# Phase 8: workbench build and local startup verification

## Goal

Finish the completed local workbench phase now that the user has installed the
React dependencies. Verify the browser artifact and actual localhost startup,
without changing backend Agent behavior.

## Task 8

- Adjust `start_workbench.ps1` so its API and frontend background processes use
  hidden windows while retaining the documented loopback ports and dry-run
  output.
- Run `npm --prefix workbench run build` and the non-interactive frontend test
  command.
- Run the API test suite and full Python regression using the installed project
  Python runtime.
- Start the local workbench, verify API health and frontend HTTP responses on
  loopback, then stop only the test-started processes so the user is not left
  with accidental background servers.
- Update the report with exact commands/results and user startup instructions.

## Constraints

- No dependency installation, no PATH modification, no public host binding,
  and no change to Agent or document-summary behavior.
- The verification must use process IDs it created and must not stop unrelated
  user processes.

## Review evidence

Write `docs/implementation/phase-8-workbench-verification-report.md` with
touched files, build/test/health evidence, cleanup evidence, and the final
startup command.
