---
name: workflow-state-manager
description: Use when Codex needs to orchestrate long-running research workflows with checkpoints, upload intake, pause/resume, human-in-the-loop decisions, artifact tracking, model/execution logs, task state files, or recovery after interruption. Triggers include workflow state, checkpoint, resume, pause task, continue research workflow, execution log, upload manifest, human intervention, agent workflow status, and research-agent demo orchestration.
---

# Workflow State Manager

Use this skill as the control layer for the research-agent workflow. It records state, routes artifacts to downstream skills, and preserves checkpoints.

## Standard Workflow

1. Create or load `workflow_state.json`.
2. Register uploaded files with `scripts/prepare_uploads.py` and write `upload_manifest.json`.
3. Before each major step, record step name, input artifacts, expected outputs, downstream skill, and start time.
4. After each step, record status, generated artifacts, result summary, and next step.
5. At human checkpoints, pause and record the user's decision.
6. On resume, read state, verify artifacts, and continue from `current_step`.

## Default Steps

`upload-intake -> academic-search-multisource -> literature-screening -> literature-matrix-extraction -> research-rag-index -> systematic-literature-review -> experiment-data-analysis -> reference-format-gbt7714 -> docx -> final-review`

## Scripts

- `scripts/init_state.py`: create a state file.
- `scripts/update_state.py`: append events and update current step.
- `scripts/resume_state.py`: print resume guidance.
- `scripts/prepare_uploads.py`: register uploaded CSV/XLSX/BibTeX/RIS/JSON/PDF/DOCX/MD/TXT/CSL files and route them to skills.

## Rules

- Never discard artifacts. Version or append instead.
- Never silently skip failed steps.
- Record human decisions in `human_decisions`.
- Record upload decisions in `upload_manifest.json`.
- Record model calls separately in `model_call_log.jsonl` when model APIs are used.
- Use `langgraph-human-in-the-loop` when checkpoint design needs workflow patterns.
