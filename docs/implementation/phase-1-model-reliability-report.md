# Phase 1 model reliability report

## Touched files

- `research_agent/tools/llm_client.py`
- `tests/test_agent_core.py`
- `docs/implementation/phase-1-model-reliability-report.md`

## Behavior delivered

`ModelGateway.complete()` now normalizes the first OpenAI-compatible choice before deciding whether it is usable final text. `NormalizedResponse` carries only safe, stable response-shape data: outcome, finish reason, text lengths, and tool-call count.

- Nonempty assistant content remains a successful remote text response and is exposed as `LLMResult.outcome == "text"`.
- Native `tool_calls`, reasoning without final content, and zero-content `finish_reason == "length"` return the existing fallback text but expose distinct `error` and `outcome` values: `native_tool_call`, `reasoning_incomplete`, and `output_exhausted`.
- Logging records response shape and lengths only; raw `reasoning_content` is never logged.
- No dependency, follow-up model call, tool-execution change, permission change, or session-storage change was introduced.

## Tests

Focused mocked-`urlopen` coverage exercises text, reasoning-only, length-exhausted, and native-tool-call payloads. The reasoning-only test also verifies that raw reasoning is absent from the model-call log while the reasoning length is retained as metadata.

Command run:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest discover -s tests -v
```

Result: `Ran 47 tests ... OK`.

## Remaining concern

The boundary reports native tool calls distinctly but deliberately does not execute or translate them; routing native provider tool calls is out of scope for this phase.

## Review fix

Native `tool_calls` now take precedence over assistant `content` during normalization, so a mixed provider payload is never exposed as final text. Added a mocked mixed-content-plus-tool-call regression test.

Verification command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest discover -s tests -v
```

Result: `Ran 48 tests ... OK`.
