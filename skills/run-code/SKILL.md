---
name: run-code
description: Execute arbitrary Python code for data analysis, statistical tests, scientific computing, plotting, and any computation task. Returns stdout, stderr, and exit code. Use when the user needs custom analysis that no pre-built tool covers.
---

# Run Code

Execute Python code in the local environment. The code runs with full access to installed packages (numpy, scipy, pandas, matplotlib, etc.). Use this for any computation task that cannot be done with respond alone.

## When to use

- Data analysis: statistical tests, distributions, correlations, regressions
- Signal processing: FFT, filtering, spectral analysis
- Visualization: generating plots and charts (save to file)
- File processing: parsing CSV/JSON/MAT/any format
- Computation: any custom calculation the user requests

## Constraints

- Timeout: 60s default, 300s max
- Code must be self-contained; cannot depend on session files unless paths are explicitly passed
- Output is returned as text; for plots, save to a file path the user can access
- Prefer concise scripts that produce clear results
