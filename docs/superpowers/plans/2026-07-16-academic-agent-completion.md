# Academic Agent Completion Implementation Plan

**Authoritative design:** `docs/superpowers/specs/2026-07-16-academic-agent-completion-design.md`

## Delivery rules

- Keep the provider-neutral, model-led agent loop and every existing general-purpose skill.
- Do not route user intent, rank research meaning, or infer scientific semantics with keyword tables, regexes, or fixed score weights.
- Keep deterministic code for operational budgets, exact filters, schema validation, statistics, chart rendering, citation standards, persistence, and safety.
- Implement each slice with a failing public-behavior test first, then the smallest production change, then focused regression tests.
- Treat provider token counts as authoritative; retain a model-call ceiling so providers that omit usage still cannot loop without bound.

## Vertical slices

### 1. Runtime safety and truthful workflow state

Add configurable per-turn model-call and token budgets at the shared provider gateway. A budget stop must make no further provider request, preserve completed artifacts and observations, persist a `budget_exhausted` event, and return an actionable message. Expose idle/running/waiting states from the active turn rather than treating persisted `active` sessions as running. Project persisted session events into generic workflow steps; unknown progress remains indeterminate.

### 2. Literature retrieval and recursive screening

Replace lexical relevance weights, aliases, domain-specific negation rules, and fixed query expansion with a strict structured model evaluation contract. Deterministic code applies explicit venue/year/language/open-access constraints, validates model output, deduplicates identifiers, enforces iteration/candidate budgets, and records why the recursion stopped.

### 3. Evidence-grounded extraction and review structure

Require structured evidence fields with source spans or explicit `not_reported` values. Remove regex-based guesses for method, dataset, innovation, findings, and conclusion. Preserve extraction provenance and expose unresolved fields instead of fabricating them.

### 4. Schema-first data analysis and charting

Inspect uploaded schemas deterministically, accept explicit model-selected column roles, methods, and chart specifications, and validate them before execution. Remove free-form request regex parsing from transformations. Produce real chart artifacts and a machine-readable analysis manifest in one workflow.

### 5. References and RAG provenance

Enrich incomplete references through public scholarly metadata sources with field-level provenance and confidence. Validate GB/T 7714 and supported style output without inventing missing metadata. Emit a retrieval manifest for every knowledge-grounded answer or artifact.

### 6. Workbench redesign and inspectors

Add persistent workflow and artifact inspectors, truthful task-state presentation, budget visibility, and the approved editorial visual direction: high-contrast serif display type, charcoal, warm cream, and muted olive accents. Keep the existing chat, file upload, plan mode, intervention, scheduling, settings, and general-agent surfaces.

### 7. Acceptance and audit

Run focused and full backend tests, frontend tests and production build, real public-source smoke tests, end-to-end browser inspection, SQLite resource checks, a hardcoding scan classified into semantic versus legitimate operational constants, and an explicit token-runaway simulation.

