---
name: web-search
description: Search the public web for current information, style guides, journal requirements, conference details, and any non-academic reference material. Returns titles, URLs, and snippets. Use when academic databases cannot answer the query.
---

# Web Search

Search the open web through one OpenCLI adapter selected explicitly by the model. The local executable currently supports `brave`, `duckduckgo`, and `google` for this tool. It does not try another adapter after an empty result or error.

## Query construction

Combine "topic + goal + constraint" for better results. Example: "Nature journal reference format author guidelines 2024".

## Output

Returns titles, URLs, and snippets for each result. After receiving results, summarize findings in natural language rather than dumping raw output.
