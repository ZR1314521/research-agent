---
name: model-call-logger
description: Record sanitized model operations, provider, model, timing, status, prompt metadata, and response metadata. Use for every planner, extraction, synthesis, or editing model call.
---

# Model Call Logger

Write append-only JSON Lines inside the active session. Never record API keys or authorization headers. Record fallback use, parse failures, latency, and errors so runs remain auditable.

