---
name: academic-search-multisource
description: Search, normalize, merge, and deduplicate papers from OpenAlex, PubMed, Semantic Scholar, and arXiv. Use for natural-language literature searches, venue scopes, year ranges, and paper-pool creation.
---

# Academic Search Multisource

Parse topic, dates, venues, sources, and result limit. `sources` is required and is chosen by the model from the available peer routes. Query only those selected public sources, preserve raw metadata, deduplicate by DOI or normalized title, and pass candidates to screening. Use bounded recursive retrieval only when requested or when the target pool is not reached.
