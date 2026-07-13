# AI Research Agent Development Coverage

## Requirement Mapping

1. Literature retrieval and recursive screening: `research_agent.nodes.literature_search` collects paper candidates from public sources or uploaded JSON; `research_agent.nodes.recursive_screen` applies bounded recursive scoring and filtering.
2. Literature extraction and review framework: `research_agent.nodes.matrix_extract` creates the evidence matrix; `research_agent.nodes.rag` builds retrieval artifacts; `research_agent.nodes.review_draft` creates a grounded outline and logs model calls.
3. Experiment statistics and visualization suggestions: `research_agent.nodes.experiment_analysis` handles uploaded CSV/TSV data and emits summary artifacts.
4. Reference formatting and audit: `research_agent.nodes.reference_format` uses `scripts/format_references_strict.py` and `rules/`.
5. Pause/resume and human intervention: `research_agent.state.RunState` stores checkpoints, human decisions, artifacts, and errors in `runs/<run_id>/workflow_state.json`.

## API Key Entry

Copy `.env.example` to `.env` and fill:

```text
RESEARCH_AGENT_LLM_PROVIDER=deepseek
RESEARCH_AGENT_LLM_MODEL=deepseek-chat
RESEARCH_AGENT_LLM_BASE_URL=https://api.deepseek.com/v1
RESEARCH_AGENT_LLM_API_KEY=your-key-here
```

Provider-specific fallbacks are also supported:

```text
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
OPENALEX_MAILTO=
PUBMED_EMAIL=
PUBMED_API_KEY=
```

No real key should be committed.

## Runtime Rule

The final agent depends on `research_agent/`, `scripts/`, and `rules/`. The project-local `skill_dist/` remains the editable skill source, and `.codex/skills/` remains a copied Codex-only target.
