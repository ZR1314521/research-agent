---
name: langgraph-human-in-the-loop
description: Apply human approval, correction, pause, and resume patterns to long research tasks. Use when an action requires confirmation or user-supplied missing data.
---

# Human In The Loop Patterns

Use the local session checkpointer; LangGraph is not a runtime dependency. Make side effects idempotent before a pause. Store pending action arguments and resume only after an explicit user decision.

