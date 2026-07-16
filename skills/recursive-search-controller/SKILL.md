---
name: recursive-search-controller
description: Run bounded query expansion and repeated calls to selected literature APIs until the target pool, no-new-term, or maximum-round stop condition is reached.
---

# Recursive Search Controller

Use the runtime-configured search boundary. Each round must issue a new source query, deduplicate against prior results, and record query terms and stop reason. Never rescore one unchanged pool recursively.
