# Phase 1: model reliability vertical slice

## Goal

Make the existing model boundary correctly classify OpenAI-compatible responses
that contain normal text, native tool calls, or reasoning without final content.
No caller may mistake a reasoning-only or token-exhausted response for a generic
`empty_model_response`, and diagnostic logging must retain response shape without
recording secrets or raw reasoning text.

## Task 1

Update the existing `research_agent/tools/llm_client.py` shared boundary rather
than adding a second client. Add a small normalized response representation and
extend `LLMResult` only as required to expose a stable outcome classification.

Required behavior:

- Read the full assistant message safely, including `content`, `reasoning_content`,
  `tool_calls`, and `finish_reason` where supplied.
- Treat a nonempty `content` as a normal success.
- Identify native tool calls without attempting to parse them as final text.
- Classify a response with reasoning but no final content as `reasoning_incomplete`.
- Classify a zero-content completion terminated for length as `output_exhausted`.
- Preserve the existing public `complete()` behavior for successful text calls.
- Keep raw reasoning text out of logs; log only shape metadata and lengths.
- Add focused unit tests using mocked `urlopen` payloads for text, reasoning-only,
  length-exhausted, and native-tool-call response shapes.

## Constraints

- Do not add a dependency.
- Do not send a second model call merely to repair an empty response in this task.
- Do not change production file permissions, tool execution, or session storage.
- Tests must run with the project Python executable and leave only ignored test data.

## Review evidence

The implementer writes `docs/implementation/phase-1-model-reliability-report.md`
with touched files, behavior, tests, and remaining concerns. The reviewer checks
those named files directly because this repository has no initial Git commit.
