---
name: data-transform
description: Transform uploaded experiment data while preserving the source file.
---

# Data Transform

Use this skill when the user asks to normalize, standardize, filter missing rows, keep selected columns, rename columns, convert tables, or save transformed data as a new CSV/XLSX file.

Rules:

- Never overwrite the source file unless the user explicitly confirms.
- Write a transformation log that records source path, output path, operations, and affected columns.
- Treat outlier deletion and missing-value deletion as separate actions; do not delete outliers automatically.
- Keep subject IDs, trial IDs, and labels as identifiers unless the user explicitly says otherwise.

