---
name: experiment-data-analysis
description: Analyze CSV, TSV, XLSX, and simple text tables for descriptive statistics, missing values, IQR outliers, trends, group comparisons, and visualization suggestions.
---

# Experiment Data Analysis

Inspect the uploaded schema before choosing analysis semantics. Supply `column_roles` explicitly with any identifier, order/time, group, and measure columns; never infer these roles from column-name keywords. Supply each intended trend in `trend_specs`, each comparison in `group_specs`, and any real image output in `chart_specs`. Preserve original files. Report assumptions, missing values, numeric summaries, row-level outlier flags, and generated chart paths. Treat outliers as review flags, not automatic deletions.
