---
name: workflow-state-manager
description: Persist terminal research sessions, checkpoints, artifacts, decisions, pause state, and execution events. Use for status, pause, resume, recovery, or any multi-turn research task.
---

# Workflow State Manager

Checkpoint after every user turn and skill execution. Store session state and append-only events under `runs/sessions/<session_id>/`. Never log API keys. Resume from the last complete event and keep human decisions explicit.

