---
name: reference-format-gbt7714
description: Parse, validate, correct, and format references in Nature, IEEE, APA, GB/T 7714, and other bundled styles. Accepts DOCX (extracts references natively), JSON, BibTeX, or RIS input. Produces a formatted Word document.
---

# Reference Format GB/T 7714

Reads DOCX files in full using python-docx — parses all paragraphs including the reference section at the end of the document. Automatically locates "References"/"参考文献" headings and extracts author, title, year, venue, DOI from each entry. Can also be used to check what format the references are currently in. Also accepts JSON, BibTeX, and RIS. Produces formatted Word document and citation audit report. Never invents metadata.

