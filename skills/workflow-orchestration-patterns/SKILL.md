---
name: workflow-orchestration-patterns
description: Guide bounded, retryable, idempotent, and auditable research task orchestration. Use when composing multiple local skills into an explicit macro task.
---

# Workflow Orchestration Patterns

Keep planning separate from side-effecting activities. Bound recursion and retries. Checkpoint after each activity. Do not invoke a macro workflow unless the user asks for the complete multi-stage outcome.

