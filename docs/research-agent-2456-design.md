# Research Agent 2/4/5/6 Design

## Scope

This package closes four gaps in the research-agent prototype:

- file upload intake and routing;
- local RAG knowledge-base construction and retrieval logs;
- bounded recursive literature search and screening;
- stricter reference formatting with GB/T 7714 plus major journal/publisher profiles.

The implementation is intentionally demo-stable: it uses local files and standard-library scripts so the workflow can run without paid APIs or secret data.

## Data Flow

1. `scripts/prepare_uploads.py` copies or registers uploaded files under `runs/<run_id>/uploads/` and writes `upload_manifest.json`.
2. `scripts/recursive_search.py` takes raw paper pools and performs up to three controlled expansion/filter rounds.
3. `scripts/build_rag_index.py` chunks public rules, uploaded papers, and extracted matrices into `rag_index/chunks.jsonl`.
4. `scripts/query_rag.py` performs lexical top-k retrieval and writes `retrieval_log.jsonl` plus `rag_answer.md`.
5. `scripts/format_references_strict.py` formats references using `rules/style_profiles.json` and downloaded CSL files as rule evidence.

## Rule Library

Public rule material lives under `rules/`:

- `rules/reference_styles/*.csl`: downloaded CSL styles for GB/T 7714, Nature, IEEE, Science, Cell, Elsevier, Springer, ACM, ACS, AMA, BMJ, NEJM, APA, RSC, and selected Chinese styles.
- `rules/raw/*.md`: official author-guide extracts gathered with OpenCLI browser/web read.
- `rules/style_profiles.json`: local profile registry used by the strict formatter.

Full copyrighted standards are not bundled. GB/T 7714 behavior is implemented from public CSL profiles plus a local rule summary and marks uncertain fields for manual checking.

## Acceptance

Run `python scripts/run_demo.py`. Expected outputs appear in `demo_runs/demo/`:

- `upload_manifest.json`
- `recursive_search_plan.json`
- `screened_papers.json`
- `rag_index/chunks.jsonl`
- `retrieval_log.jsonl`
- `references_gbt7714_numeric.md`
- `references_ieee.md`
- `references_nature.md`
- `citation_check_report.md`
