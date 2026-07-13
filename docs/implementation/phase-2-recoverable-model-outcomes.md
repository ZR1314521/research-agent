# Phase 2: recoverable model outcomes

## Goal

Make the user-facing agent distinguish a provider outage from a model response
that was incomplete because of reasoning or output exhaustion. The task must
preserve the completed result and present an honest, actionable recovery state.

## Task 2

Change the smallest shared caller path necessary after `LLMClient.complete()`
returns the classifications introduced in Phase 1.

Required behavior:

- `reasoning_incomplete` and `output_exhausted` must not tell the user that the
  model address, API key, or service is unavailable.
- Both outcomes leave the session recoverable: status `waiting_user`, a
  `pending_action` that can represent retrying the current request, and a clear
  Chinese message that names the actual condition and says no tool ran.
- Transport/configuration failures retain the current unavailable-model message.
- The failure event records the specific outcome but never raw model reasoning.
- Native tool-call outcomes remain a distinct unsupported-provider capability
  error; do not pretend the requested tool ran.
- Add focused tests at the AgentLoop level for reasoning-incomplete,
  output-exhausted, native-tool-call, and ordinary unavailable-model behavior.

## Constraints

- Do not add automatic cross-provider fallback, a second model call, or tool
  execution in this phase.
- Do not modify document, research, file, or session persistence services.
- Reuse the Phase 1 `LLMResult.outcome` classification; do not inspect raw API
  response payloads in the agent loop.

## Review evidence

The implementer writes `docs/implementation/phase-2-recoverable-model-outcomes-report.md`
with touched files, behavior, tests, and remaining concerns. The reviewer checks
those named files directly because this repository has no initial Git commit.
