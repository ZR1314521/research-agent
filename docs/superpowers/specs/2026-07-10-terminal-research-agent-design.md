# Terminal Research Agent Design

## Goal

Build a standalone, terminal-first research agent. The runtime must load all
skills, rules, scripts, and state from this project. It must never read
`~/.codex/skills` or depend on another agent.

The model is replaceable infrastructure, not the product identity. A configured
model plans the next action. Local Python code executes searches, file work,
statistics, formatting, state persistence, and logs.

## Interaction Model

The default entry point is a persistent terminal conversation:

```text
Research> Find CNN BCI EEG papers from the last three years and save them.
[plan] academic-search-multisource
[run] literature-search-openalex
[run] semanticscholar-skill
[done] 12 screened papers
Agent> I found these papers. Review the list before I continue.

Research> What is each paper about?
[plan] literature-matrix-extraction
Agent> ...
```

No domain workflow runs automatically. Each turn follows a small agent loop:

```text
user message -> plan -> validate -> execute local skill -> observe -> reply
```

A bounded macro workflow is available only when the user explicitly requests a
complete literature review or another multi-stage task.

## Runtime Layout

```text
skills/                 local skill packages and registry.json
research_agent/         terminal, planner, sessions, executor, capabilities
rules/                  CSL files and public journal/reference rules
scripts/                deterministic standalone helpers
workflows/              optional macro workflow recipes
runs/sessions/<id>/     session state, artifacts, execution and model logs
skill_dist/             maintenance snapshots; never read by runtime
```

Each skill folder contains a concise `SKILL.md`. `skills/registry.json` is the
machine-readable execution contract. It records whether a skill is a direct
tool, prompt transformation, or internal design reference, plus its handler.

## Local Skill Set

The project ships these 24 names:

1. workflow-state-manager
2. academic-search-multisource
3. literature-screening
4. literature-matrix-extraction
5. experiment-data-analysis
6. reference-format-gbt7714
7. systematic-literature-review
8. read-arxiv-paper
9. 20-ml-paper-writing
10. docx
11. doc-coauthoring
12. humanizer
13. canvas-design
14. literature-search-openalex
15. pubmed-database
16. semanticscholar-skill
17. langgraph-human-in-the-loop
18. workflow-orchestration-patterns
19. file-upload-router
20. workflow-visualizer-dashboard
21. rag-vector-knowledge-base
22. recursive-search-controller
23. gbt7714-strict-rules
24. model-call-logger

The local `docx` skill is an independent implementation. Restricted upstream
prompt and script files are not copied.

## Model Contract

Configuration remains environment based:

```env
RESEARCH_AGENT_LLM_PROVIDER=
RESEARCH_AGENT_LLM_BASE_URL=
RESEARCH_AGENT_LLM_MODEL=
RESEARCH_AGENT_LLM_API_KEY=
```

The first adapter uses the OpenAI-compatible `/chat/completions` protocol. The
planner requests strict JSON and does not require provider-native tool calling.
A deterministic intent router handles common research commands when a model is
missing or returns invalid JSON.

## Session State

Every turn is checkpointed in `session.json`. State includes messages, active
paper pool, artifacts, pending user decision, pause state, and event history.
Append-only files contain model calls and execution events. Secrets are never
written to logs.

Built-in terminal commands:

```text
/help /skills /status /pause /resume /new /exit
```

## Capability Rules

- Search is multi-source and bounded to three recursive retrieval rounds.
- Recursion must issue new source queries; rescoring one pool is not recursion.
- Every excluded paper keeps an auditable reason.
- Extraction uses only supplied abstracts or full text and marks insufficient
  evidence instead of inventing results.
- RAG uses local sparse TF-IDF vectors and records source paths and scores.
- Data analysis supports CSV, TSV, XLSX, and text tables when parsable.
- Reference formatting preserves original metadata and emits an audit report.
- Any expensive or ambiguous continuation can become a pending human decision.

## Development Acceptance

1. `start_agent.bat` opens a persistent terminal prompt.
2. `/skills` reports all 24 local skills with no external skill path.
3. A natural-language search request creates a session paper pool and artifacts.
4. A follow-up summary request uses that same paper pool without searching again.
5. Pause, exit, and resume retain the session.
6. Data and reference requests route to their corresponding local skills.
7. Tests run without network or an API key by using fixtures and deterministic
   planning.
8. Optional live smoke tests can use configured public APIs and model service.
