# Phase 2 recoverable model outcomes report

## Touched files

- `research_agent/core/agent.py`
- `tests/test_agent_core.py`
- `docs/implementation/phase-2-recoverable-model-outcomes-report.md`

## Behavior delivered

`AgentLoop` now consumes the Phase 1 `LLMResult.error` / `outcome`
classification at its existing shared failed-model caller path. It does not
read provider payloads or raw reasoning.

- `reasoning_incomplete` and `output_exhausted` now produce Chinese,
  condition-specific recovery messages. They do not suggest the model URL,
  API key, or service is unavailable.
- Each incomplete outcome sets `session.status` to `waiting_user` and stores a
  `pending_action` of type `retry_current_request`, including the original
  request and normalized outcome. The message states that no tool ran and that
  the session and completed artifacts are retained.
- The corresponding failed session event stores `outcome` as the normalized
  classification only. No raw model reasoning is accepted or written by the
  agent loop.
- `native_tool_call` remains a separate unsupported-provider-capability error;
  its message says the native tool call was not run and it creates no retry
  action that could imply tool execution.
- Transport and configuration errors retain the prior unavailable-model
  message, including the configuration checks.

No fallback provider, repair model call, tool execution, persistence-service
change, document change, or research/file service change was added.

## Tests

Focused AgentLoop coverage was added for reasoning-incomplete,
output-exhausted, native-tool-call, and ordinary unavailable-model outcomes.
Each outcome test guards the executor so it fails if a tool is called.

Focused command run:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_agent_core.AgentCoreTests.test_reasoning_incomplete_waits_for_a_retry_without_running_a_tool tests.test_agent_core.AgentCoreTests.test_output_exhausted_waits_for_a_retry_without_running_a_tool tests.test_agent_core.AgentCoreTests.test_native_tool_call_is_an_unsupported_provider_error_without_running_a_tool tests.test_agent_core.AgentCoreTests.test_transport_failure_keeps_the_unavailable_model_message -v
```

Result: `Ran 4 tests ... OK`.

Full command run:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest discover -s tests -v
```

Result: `Ran 52 tests ... OK`.

## Remaining concern

`retry_current_request` records an explicit, safe recovery intent; the current
chat UI still requires the user to submit the retry, which is intentional for
this phase because automatic replays and second model calls are out of scope.

## Review fix

The recovery path now receives `LLMResult.outcome` separately from `error` and
uses the normalized outcome as the authoritative branch key. This applies to
the original decision call and the JSON-repair call. A classified non-text
repair result therefore reaches the same recoverable outcome handling instead
of being passed to `Decision.from_text()` as empty text.

Added focused coverage for repair-call `reasoning_incomplete` and
`output_exhausted`, plus a fixture where `error` is a timeout while `outcome`
is `reasoning_incomplete`; it verifies that the outcome-specific recovery state
and message win.

Verification command:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_agent_core.AgentCoreTests.test_reasoning_incomplete_waits_for_a_retry_without_running_a_tool tests.test_agent_core.AgentCoreTests.test_output_exhausted_waits_for_a_retry_without_running_a_tool tests.test_agent_core.AgentCoreTests.test_repair_reasoning_incomplete_waits_for_a_retry tests.test_agent_core.AgentCoreTests.test_repair_output_exhausted_waits_for_a_retry tests.test_agent_core.AgentCoreTests.test_model_outcome_is_authoritative_over_error tests.test_agent_core.AgentCoreTests.test_native_tool_call_is_an_unsupported_provider_error_without_running_a_tool tests.test_agent_core.AgentCoreTests.test_transport_failure_keeps_the_unavailable_model_message -v
```

Exact result: `Ran 7 tests in 0.066s ... OK`.
