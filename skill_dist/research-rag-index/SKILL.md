---
name: research-rag-index
description: Use when Codex needs to build or query a local RAG knowledge base for academic papers, literature matrices, public author guidelines, GB/T7714 rules, CSL files, uploaded Markdown/Text/JSON/CSV documents, or research-agent demo evidence. Produces chunks, retrieval logs, and grounded answer drafts without using secret data.
---

# Research RAG Index

Use this skill to build a local retrieval layer for the research-agent system.

## Workflow

1. Collect public inputs: `screened_papers.json`, `literature_matrix.csv`, uploaded notes, public author guidelines, CSL files, and GB/T7714 rule summaries.
2. Run `scripts/build_rag_index.py <inputs...> --out-dir rag_index`.
3. Query with `scripts/query_rag.py --index-dir rag_index --query "<question>"`.
4. Save `chunks.jsonl`, `inverted_index.json`, `index_meta.json`, `retrieval_log.jsonl`, and `rag_answer.md`.

## Rules

- Do not index涉密 or private data unless the user explicitly provides it for local processing.
- Keep every chunk source path in the output.
- Keep retrieval logs auditable.
- Treat the bundled lexical index as demo-grade. For production, replace it with embeddings plus Chroma, FAISS, or another vector store.
- Do not let RAG evidence override user-provided journal-specific instructions.

## Scripts

- `scripts/build_rag_index.py`: chunks supported files and builds a local lexical index.
- `scripts/query_rag.py`: retrieves top-k chunks and writes a grounded answer draft.
