# Phase 4 document-summary report

## Test order and results

1. Added `AcceptanceTests.test_explicit_docx_explanation_returns_summary_and_preserves_source`.
   The first run exposed a local test-environment gap (`ModuleNotFoundError: No module named 'docx'`), so the fixture was changed to a minimal standard-library DOCX ZIP; this did not add a dependency. The next RED run failed as intended because the request routed to `academic-search-multisource` instead of `document-summary`. After the minimal routing, contract, executor, and service changes, the exact command below passed.
2. Added `AcceptanceTests.test_explicit_markdown_explanation_uses_document_summary`. It passed through the same direct route.
3. Added `RuntimeHardeningTests.test_document_convert_accepts_md_alias`. The RED run raised `ValueError: target_format must be markdown or docx`; mapping `md` to `markdown` made the exact command below pass.
4. Added `AgentCoreTests.test_document_summary_prompt_carries_request_and_evidence_boundary`. It verifies that the prompt includes the user request, detail level, and the explicit unsupported-claim prohibition. It was written but not run before the parent-directed stop.

## Behavior

`document-summary` is an executable local capability for an explicit DOCX,
Markdown, or `.markdown` path. It reads text without modifying the source,
asks `WritingService` for a concise Chinese evidence-grounded answer (or a
local evidence-bounded fallback), writes `document_summary.md`, and returns
that summary as the tool message. The system prompt specifically tells the
configured model to use it rather than treat upload or conversion as the final
answer. `document-convert` remains conversion-only and now accepts `md` as the
`markdown` alias.

## Touched files

- `research_agent/capabilities/documents.py`
- `research_agent/capabilities/writing.py`
- `research_agent/executor.py`
- `research_agent/intent.py`
- `research_agent/planner.py`
- `research_agent/prompts/agent_system.md`
- `research_agent/skill_registry.py`
- `skills/registry.json`
- `skills/document-summary/SKILL.md`
- `tests/test_research_agent_acceptance.py`
- `tests/test_runtime_hardening.py`
- `tests/test_agent_core.py`

## Exact test commands and observed results

Passed:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_research_agent_acceptance.AcceptanceTests.test_explicit_docx_explanation_returns_summary_and_preserves_source
# Ran 1 test in 0.027s — OK

.\.venv\Scripts\python.exe -m unittest tests.test_research_agent_acceptance.AcceptanceTests.test_explicit_markdown_explanation_uses_document_summary
# Ran 1 test in 0.026s — OK

.\.venv\Scripts\python.exe -m unittest tests.test_runtime_hardening.RuntimeHardeningTests.test_document_convert_accepts_md_alias
# Ran 1 test in 0.013s — OK
```

Not run before the requested stop:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_agent_core.AgentCoreTests.test_document_summary_prompt_carries_request_and_evidence_boundary
```

## Remaining concern

The local `.venv` does not contain `python-docx`; the implementation uses it
when available and has a read-only DOCX XML fallback for the focused test, but
the full suite still needs to be run in the intended dependency environment.

## Stabilization follow-up

`DocumentService.readable_text` now falls back to the existing read-only
`word/document.xml` extraction when `python-docx` is unavailable **or cannot
open the supplied DOCX**. This keeps the source read-only and lets
`WritingService` complete the same direct summary operation.

Passed after this change:

```powershell
& 'C:\Users\Z18803231258\AppData\Local\Python\bin\python.exe' -m unittest tests.test_research_agent_acceptance.AcceptanceTests.test_explicit_docx_explanation_returns_summary_and_preserves_source
# Ran 1 test in 0.096s — OK
```
