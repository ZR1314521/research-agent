---
name: academic-search-multisource
description: Use when Codex needs multi-source academic literature retrieval across OpenAlex, PubMed, Semantic Scholar, and arXiv; combines search results into one normalized paper pool for downstream screening, recursive search expansion, literature matrix extraction, review writing, RAG indexing, or citation formatting. Triggers include multi-source literature search, academic search, paper pool, recursive literature retrieval, venue-scoped retrieval, and precise literature pool creation.
---

# Academic Search Multisource

Use this skill to create a normalized paper pool, then optionally run bounded recursive screening.

## Routing

- OpenAlex: use `literature-search-openalex`.
- PubMed: use `pubmed-database`.
- Semantic Scholar: use `semanticscholar-skill`.
- arXiv: use `systematic-literature-review` for SLR-style search or `read-arxiv-paper` for single papers.

## Standard Workflow

1. Parse topic, keywords, date range, venue scope, database scope, and max results.
2. Run selected source searches.
3. Save raw source results separately.
4. Normalize and merge raw results with `scripts/merge_paper_pool.py`.
5. For recursive retrieval, run `scripts/recursive_search.py` with bounded rounds and stop conditions.
6. Output `papers.json`, `screened_papers.json`, `excluded_papers.json`, `recursive_search_plan.json`, and `screening_log.md`.
7. Pass screened papers to `literature-matrix-extraction` and `research-rag-index`.

## Recursive Search Rules

- Never run unbounded recursion.
- Default to at most 3 rounds.
- Stop when target paper count is reached, no new terms appear, or the user stops the workflow.
- Preserve every exclusion reason in `excluded_papers.json`.
- Keep venue and year filters explicit in `recursive_search_plan.json`.

## Scripts

- `scripts/merge_paper_pool.py`: normalize and merge raw source results.
- `scripts/recursive_search.py`: controlled recursive expansion, scoring, filtering, and audit logs.

## Rules

- Do not screen aggressively during source collection.
- Preserve raw metadata in `raw_metadata`.
- Mark missing DOI or abstract as empty, not fabricated.
