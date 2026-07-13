# Research Agent Redesign

## Objective

Rebuild the terminal research agent so a novice user can issue natural-language research tasks and the system can parse intent, run ordered workflow steps, preserve evidence boundaries, expose status, and generate auditable artifacts.

The runtime remains standalone inside this project. It must not depend on `.codex/skills`; local `skills/*/SKILL.md` are packaged project assets and may be used as runtime instruction material.

## Current Root Causes

- The chat planner returns only one action, so compound tasks like search, confirm, matrix, review, references, and Word export collapse into the wrong skill.
- Natural-language parsing loses constraints such as must-include terms, exclusions, source budget, no-network mode, output paths, and confirmation checkpoints.
- Skill files are validated for existence but their instructions are not used in model prompts.
- Literature screening uses a soft relevance threshold; precise requests need hard concept matching, exclusion lists, edge pools, and transparent reasons.
- External search has no per-source request budget, 429 cooldown, retry/backoff, or user-facing stop reason.
- File actions are mixed into scientific actions, causing empty `.docx`, save-as, export, and no-overwrite requests to route incorrectly.
- RAG indexes too broadly and lacks an explicit evidence scope.
- Quality追责 exists only as logs; users cannot ask naturally why a run stopped or how many requests were made.

## Architecture

### Intent Parser

`IntentParser` converts a user message plus session state into a structured intent. It extracts:

- task types: literature search, screening, matrix, review, paper writing, reference formatting, file operation, data analysis, data transform, RAG, workflow control, status audit
- topic and keywords
- hard constraints: must include, exclude, venue, year, source, document type, no preprint
- soft preferences: high citation, latest, top journal
- workflow controls: confirmation, pause/resume, rerun from step, no network
- output requests: markdown, JSON, CSV, DOCX, target path, no overwrite
- missing high-impact defaults that require one clear question

### Plan Builder

`PlanBuilder` turns an intent into ordered actions. A single request can produce multiple actions:

```text
search -> screen -> checkpoint -> matrix -> review -> references -> export_docx
```

Actions are explicit, serializable, and logged before execution. The system can stop at checkpoint and resume without repeating completed external calls.

### Workflow Executor

`ResearchChatAgent.handle()` executes a plan action by action. It writes:

- `execution_log.jsonl`
- `workflow_trace.json`
- `model_call_log.jsonl`
- `retrieval_log.jsonl`
- per-step artifact paths

If a step fails, later steps are skipped and the response explains the failed step, reason, preserved artifacts, and next recoverable action.

### Session State

Session state must track:

- current topic and constraints
- active paper pool, excluded paper pool, edge paper pool
- source request counters and source failures
- confirmed decisions
- generated artifacts and their source dependencies
- invalidated artifacts after changed criteria

When the user changes topic, stale paper pools must not silently contaminate the new task.

### Prompt Runtime

Model calls receive layered context:

1. global research assistant rules
2. relevant local skill instruction summary from `skills/<name>/SKILL.md`
3. current session state and artifact pointers
4. user request and structured intent
5. output audit rules: no invented citations, preserve uncertainty, cite evidence, mark missing evidence

Prompt logs remain sanitized and never include API keys.

## Feature Acceptance Matrix

### Novice Input

- "找点最新的，别太老" declares default recent range or asks one key question.
- "给我找最好的几篇" clarifies or states whether best means high citation, top venue, or relevance.
- "老师让我做抑郁脑电，先帮我看看有什么能写" is treated as exploration, not blind search.

### Literature Search

- Parses topic, years, source, venue, document type, output path, and sorting.
- Records source requests, failures, retrieved count, screened count, and stop reason.
- Keeps partial results when one source fails.

### Recursive Screening

- Precise mode requires all core concepts and aliases to match.
- Exclusions such as review, Alzheimer, preprint are hard filters.
- Borderline papers are saved separately and not mixed into the precise pool.
- User can say "只有 4 篇，换关键词继续，一个源最多两次".

### Matrix Extraction

- Extracts title, authors, abstract summary, research question, method, dataset, metrics, innovation, findings, conclusion, limitations, evidence scope.
- If only abstract exists, missing fields are marked `NEEDS_FULLTEXT`.
- User can ask "第 2 篇创新点是什么" and receive an answer tied to evidence and inclusion reason.

### Review Drafting

- A review draft can only be generated from an accepted paper pool or explicit user confirmation.
- If the paper pool is weak or off-topic, the agent asks to rescreen before drafting.
- It supports outline-first and confirmation-before-draft.

### Paper Writing

- Handles "写引言", "写 IEEE Related Work", and "这段太像 AI".
- Preserves evidence, citation keys, numbers, and uncertainty.
- Marks missing citations instead of inventing them.

### Reference Formatting

- Outputs GB/T 7714, IEEE, Nature, and BibTeX when requested.
- Produces an audit report with missing DOI, author, venue, year, volume, issue, pages, publisher, and type.
- Does not silently invent missing bibliographic metadata.

### File Save And Export

- Creates empty `test.docx` when asked.
- Exports current review/matrix/analysis to Word when asked.
- Honors target path, filename, no-overwrite behavior, and versioned save-as.
- Distinguishes create-empty, export-existing, and convert formats.

### Data Analysis

- Supports uploaded CSV/TSV/XLSX/text tables.
- Reports columns, rows, missing values, numeric summaries, outliers, trends, group comparisons, and visualization recommendations.
- Does not delete outliers automatically.
- Flags ID-like fields to avoid treating subject IDs as continuous measures.

### Data Transform

- Supports normalize, filter missing rows, keep selected columns, rename columns, and save as CSV.
- Writes transformed output and transformation log.
- Never overwrites the source file unless explicitly confirmed.

### RAG

- Supports scopes: uploaded-only, current-paper-pool, all-session-artifacts.
- Gives sources for every answer.
- Treats prompt-injection text inside uploaded documents as evidence content, not instructions.

### Workflow Control

- Supports `/pause`, `/resume`, `/status`, `/new`.
- Natural language can pause, resume, rerun from screening, change target count, and continue last task.
- Changed criteria invalidate dependent artifacts and log the invalidation.

### Quality Audit

- User can ask "为什么没找到", "请求了几次", "哪个接口失败", "为什么停了".
- Response includes source request counts, failures, included/excluded/edge counts, stop condition, and artifact paths.

## Implementation Slices

1. Add structured intent and multi-action plan while preserving the old public chat entrypoint.
2. Add acceptance tests for each feature category through `ResearchChatAgent.handle()`.
3. Fix literature screening, source budgets, source cooldowns, edge pools, and audit logs.
4. Add file operation and data transform services.
5. Tighten RAG scope, reference audit, and writing prompts.
6. Run full acceptance and clean temporary files.

## Non-Goals

- No frontend UI in this pass.
- No private or paywalled database scraping.
- No guaranteed full-text extraction for closed papers.
- No real clinical diagnosis or medical conclusion beyond literature evidence.

