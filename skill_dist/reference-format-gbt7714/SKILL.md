---
name: reference-format-gbt7714
description: Use when Codex needs to format, convert, check, or correct academic references in GB/T 7714, Nature, IEEE, Science, Cell, Elsevier, Springer, ACM, ACS, AMA, BMJ, NEJM, APA, BibTeX, or CSL-like styles; verifies DOI/arXiv metadata, fixes author/year/title/venue fields, checks citation-reference consistency, and produces style-specific audit reports.
---

# Reference Format GB/T 7714

Use this skill to normalize references, format them, and audit missing or suspicious metadata.

## Workflow

1. Load references from DOI list, BibTeX, RIS, `papers.json`, `screened_papers.json`, `literature_matrix.csv`, or JSON reference lists.
2. Normalize authors, title, year, venue, volume, issue, pages, DOI, and URL.
3. Use `references/style_profiles.json` to choose profile behavior.
4. Use downloaded CSL files under `references/reference_styles/` as local style evidence.
5. Run `scripts/format_references_strict.py`.
6. Mark uncertain fields as `NEEDS_CHECK`.
7. Produce style outputs and `citation_check_report.md`.

## Supported Profile Families

- GB/T 7714-2015 numeric and author-date.
- Nature, Science, Cell.
- IEEE, ACM.
- Elsevier Vancouver, Elsevier Harvard.
- Springer Vancouver.
- ACS, AMA, BMJ, NEJM, APA.
- Selected Chinese styles available through CSL, such as Acta Physica Sinica and Chinese Medical Journal.

## Rules

- Do not fabricate DOI, venue, volume, issue, pages, or URL fields.
- Do not claim official legal compliance if the target journal has stricter local instructions not provided by the user.
- Preserve original metadata.
- Always produce a `citation_check_report.md`.
- When user provides a journal-specific author guide, add or update a profile instead of forcing GB/T rules onto that journal.

## Scripts

- `scripts/format_references.py`: lightweight formatter.
- `scripts/format_references_strict.py`: stricter multi-style formatter with audit report.
