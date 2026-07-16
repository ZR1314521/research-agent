---
name: reference-format-gbt7714
description: Parse, validate, correct, and format references in Nature, IEEE, APA, GB/T 7714, and other bundled styles. Accepts DOCX (extracts references natively), JSON, BibTeX, or RIS input. Produces a formatted Word document.
---

# Reference Format GB/T 7714

When records have a DOI and missing fields, request `enrich_metadata: true` to resolve exact DOI metadata from the public Crossref API. Never replace user-supplied fields silently and always return the field-level provenance manifest. Format and validate the normalized records; leave unresolved metadata visible for human review.

Reads DOCX files in full using python-docx — parses all paragraphs including the reference section at the end of the document. Automatically locates "References"/"参考文献" headings and extracts author, title, year, venue, DOI from each entry. Can also be used to check what format the references are currently in. Also accepts JSON, BibTeX, and RIS. Produces formatted Word document and citation audit report. Never invents metadata.
