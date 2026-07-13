# Phase 4: direct document summary delivery

## User-visible failure being fixed

When a user asks in Chinese what an explicitly supplied DOCX paper says, the
runtime can upload or convert the file and then finish the turn with an internal
artifact message. It does not deliver the requested summary. The replay is in
`C:\Users\Z18803231258\Desktop\night.txt`.

## Root cause

The planner has no direct document-summary capability. It treats upload and
conversion as terminal actions when the model says `after_success=finish`.
Conversion also rejects the common `target_format=md` alias although the model
regularly emits it.

## Task 4

Add the smallest public capability that directly fulfills this request.

- Register an executable local `document-summary` skill whose inputs are an
  explicit DOCX/Markdown path and the user's request.
- It extracts readable text from DOCX or Markdown, asks the configured model
  for a Chinese evidence-grounded explanation at a detail level inferred from
  the request, writes a `document_summary.md` artifact, and returns the summary
  itself as the user-facing message.
- It must preserve the source file and never return raw DOCX bytes or merely a
  conversion path as the completed answer.
- The model prompt must request a concise Chinese summary unless the user asks
  for detail; it must separate the paper's problem, method, evidence, and
  limitations without inventing facts.
- Add the tool contract, executor route, local skill instruction, and focused
  system-prompt rule so an explicit request to explain a DOCX selects this
  capability rather than upload or format conversion.
- `document-convert` must accept `md` as an alias for `markdown`; this remains
  a conversion-only behavior and must not be used as the direct summary result.

## Test-first acceptance

1. A DOCX with known text, when routed to `document-summary`, returns the
   generated Chinese summary in the completed agent message and stores a summary
   artifact; it does not return an upload or conversion message.
2. The source DOCX hash is unchanged after summarization.
3. Markdown source follows the same summary path.
4. `document-convert` accepts `target_format=md` and produces Markdown.
5. The summary prompt carries the actual user request and explicitly prohibits
   unsupported claims.

## Constraints

- Reuse existing `WritingService`, `DocumentService`, contracts, registry, and
  `python-docx`; do not introduce a PDF reader, browser automation, new model
  provider, or a generic workflow engine.
- The new tool must be one completed user-facing operation. Do not add a forced
  outline/checkpoint.
- First write the smallest failing public-behavior test, then implement only
  enough for it, and iterate through the acceptance list.

## Review evidence

Write `docs/implementation/phase-4-document-summary-report.md` with test order,
touched files, behavior, exact tests, and remaining concerns. The reviewer reads
the named files directly because there is no initial Git baseline.
