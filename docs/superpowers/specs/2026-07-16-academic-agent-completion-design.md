# Academic Research Agent Completion Design

## Goal

Complete the academic capability layer of the existing local Research Agent so it can be run and demonstrated against the stated requirements without turning the product into a fixed academic wizard.

The completed system must:

1. Perform multi-source literature retrieval, recursive refinement, semantic screening, deduplication, and provenance-preserving paper-pool delivery.
2. Extract grounded paper evidence and produce review outlines and draft frameworks without inventing unavailable fields.
3. Analyze uploaded tabular or text experiment data and produce verified statistics, anomaly flags, trend results, and real chart artifacts.
4. Normalize, enrich, audit, and format references in GB/T 7714 and the existing supported style corpus.
5. Persist and visualize actual workflow execution, including pause, intervention, approval, recovery, and artifacts.
6. Build RAG indexes only from explicitly selected public or uploaded sources and retain source provenance.
7. Preserve all existing general-agent capabilities, including ordinary chat, files, shell, Git, web, document conversion, writing, scheduling, and settings.

## Non-goals

- Do not replace the model-led agent loop with a fixed search-screen-extract-review pipeline.
- Do not add a keyword router or interpret user intent with regular expressions in planner-visible academic tools.
- Do not remove general-agent skills or isolate academic features into a separate product.
- Do not claim that a running task has a numeric percentage unless the runtime has a real finite plan with measurable completed steps.
- Do not fabricate evidence when a model, source, parser, or metadata resolver fails.
- Do not bundle confidential data or unlicensed copies of standards, papers, or datasets.
- Do not rewrite the React application or migrate its styling stack.
- Do not perform unrelated cleanup solely for code aesthetics.

## Architectural Invariants

The current runtime remains a model-led conversation and tool loop. The configured model decides what the user means, which skills to call, and whether another tool call is needed. Application code remains responsible for schemas, deterministic computation, source adapters, validation, permissions, persistence, cancellation, and truthful delivery.

The following distinctions define the no-hard-coding rule:

### Semantic decisions belong to the model

- interpreting the research question
- proposing or refining search queries
- judging semantic relevance
- selecting analysis variables and methods from a supplied schema
- identifying a paper's claimed method, innovation, findings, and limitations
- choosing how to organize a review
- resolving ambiguous reference candidates

### Deterministic rules belong to code

- API and artifact schemas
- exact year, venue, type, and user-supplied inclusion or exclusion constraints
- DOI and normalized-title deduplication
- statistical formulas and explicit outlier methods
- chart rendering operations
- bibliographic style rules and parsers
- state machines, permissions, rate limits, cancellation, validation, and file safety
- capability enums such as supported chart types or citation styles

No academic tool may inspect a free-form `request` string to choose domain behavior when the same decision can be represented as an explicit structured argument.

## Chosen Product Shape

Keep one browser-first Research Agent workbench with a reusable scientific capability layer. Academic work remains available through natural-language chat and the same generic tool registry as all other capabilities.

The workbench adds two generic presentation surfaces:

1. A persisted workflow trace projected from actual runtime events.
2. Typed artifact inspectors selected from artifact contracts, not research keywords.

This avoids both weak chat-only delivery and fixed four-page academic wizards.

## Literature Retrieval and Recursive Screening

### Source adapters

Retain the existing OpenAlex, PubMed, Semantic Scholar, and arXiv adapters. Source selection is an explicit tool argument supplied by the model. Enabled data-source settings and privacy policy constrain which requested adapters may run.

Adapters normalize results into one paper schema containing stable identity, title, authors, abstract, year, venue, DOI, URLs, citation count, open-access location, raw source metadata, and source provenance.

Network errors, rate limits, unsupported filters, and partial source failures remain visible per source. A failed source must not erase successful results from other sources.

### Recursive decision model

Replace fixed stopwords, domain aliases, weighted lexical relevance, and frequency-based query expansion with a structured semantic evaluator using the configured model gateway.

The evaluator uses the same provider-neutral model configuration as the main agent. It does not require a second provider, a hard-coded model name, or a separately hosted semantic service.

For each round, the evaluator receives:

- the original research objective
- explicit hard constraints
- the current query and source list
- normalized new candidates
- previously included, edge, and excluded identities
- the remaining configurable round and request budget

It returns a validated decision object:

- per-paper identity
- `include`, `edge`, or `exclude`
- relevance score and concise evidence-based reasons
- evidence scope used for the decision
- proposed next queries and rationale
- whether another round is useful
- a stop reason when iteration should finish

Exact user constraints are applied before semantic evaluation. The model cannot override a requested year range, venue restriction, content exclusion, network restriction, or source budget.

The recursion limit is a configurable emergency bound, not a keyword-derived workflow. The evaluator may stop earlier for target sufficiency, saturation, source failure, or lack of a useful refinement.

### Failure behavior

If semantic evaluation fails, preserve the raw normalized pool and round trace, mark screening as incomplete, and return a recoverable error. Do not fall back to lexical weights or silently label papers as relevant.

### Outputs

- normalized raw paper pool
- included paper pool
- edge-paper pool
- excluded-paper pool with reasons
- round-by-round JSON trace
- human-readable paper-pool report
- source request and provenance manifest

The trace records real counts for retrieved, new, deduplicated, included, edge, and excluded items per round.

## Evidence Extraction and Review Generation

### Evidence record

Each extracted row uses a stable schema:

- paper identity and citation key
- title, authors, year, venue, DOI, and source URL
- abstract summary
- research question
- method
- dataset or cohort
- innovation
- key findings
- conclusion
- limitations
- evidence scope (`metadata`, `abstract`, or `full_text`)
- missing fields and extraction warnings

The model receives only the available paper evidence and returns rows keyed to supplied paper identities. The service validates identity coverage, field types, and evidence scope before creating artifacts.

### No semantic fallback

Remove regex sentence guessing for method, dataset, innovation, findings, or conclusion. If model extraction is unavailable or invalid, retain bibliographic metadata and mark semantic fields as unavailable. The system may still deliver a partial matrix, but it must disclose that extraction is incomplete.

### Review outputs

The existing outline and draft stages remain independent capabilities. The model may call either stage when the user's request and available artifacts support it; code does not force a mandatory sequence.

Review generation must:

- ground sections in the evidence matrix or supplied paper pool
- use paper identities or citation keys
- distinguish abstract-only from full-text evidence
- preserve uncertainty and evidence gaps
- reject empty, generic, or citation-free output when evidence exists

Outputs include JSON, CSV, Markdown evidence matrices, per-paper notes, review outline, draft, and a quality report.

## Experiment Statistics and Visualization

### Schema-first analysis

The data tool first exposes a deterministic schema profile: columns, inferred primitive types, missingness, cardinality, sample values, and row count. It does not infer research meaning from column names.

The model converts the user's goal and the schema profile into an explicit analysis specification containing:

- identifier columns, if any
- grouping columns, if any
- ordered or time columns, if any
- metrics
- requested descriptive statistics
- explicit outlier method and parameters
- requested trend or group comparisons
- chart specifications

If required roles are ambiguous, the model asks the user or chooses a clearly disclosed assumption. The deterministic executor never searches the free-form request for words such as `subject`, `trial`, `normalize`, or `drop`.

### Deterministic execution

Use the existing project data stack to load CSV, TSV, TXT, XLSX, and XLSM. Compute only the requested supported statistics. Preserve the source data and create separate result artifacts.

The first completion slice supports:

- row and column profile
- missing-value summary
- count, mean, median, standard deviation, minimum, quartiles, and maximum
- IQR or z-score anomaly flags when explicitly requested
- ordered linear trend summaries
- grouped descriptive summaries
- structured warnings for insufficient or nonnumeric data

The same analysis call accepts explicit chart specifications. It delegates rendering to the existing chart service and returns real PNG or SVG artifacts together with the statistics, avoiding an unreliable hidden second workflow while preserving model control over chart choice.

### Outputs

- analysis JSON
- readable Markdown report
- anomaly flags CSV
- optional profiled or annotated dataset
- one or more verified chart artifacts
- analysis assumptions and warnings

## Reference Normalization, Enrichment, and Formatting

Retain deterministic parsing and the existing broad style-profile corpus. Standard formatting rules are an appropriate code responsibility and are not semantic routing.

Add an enrichment stage using public metadata sources such as Crossref and OpenAlex. Exact DOI matches may be applied deterministically. Ambiguous title or author candidates are presented to the semantic evaluator, which returns a structured match decision and rationale.

Every enriched field stores:

- original value
- resolved value
- source URL or identifier
- resolution method
- confidence or unresolved state

Formatting never overwrites the source document. The quality report lists missing fields, corrections, unresolved candidates, in-text citation mismatches, and the final output paths.

The existing style selector remains a one-action user affordance, but it must operate on an explicit current reference/document artifact and show a useful error when no suitable source exists.

## RAG and Public Knowledge Provenance

The local RAG service indexes only explicitly selected sources:

- uploaded user files
- normalized literature metadata and abstracts
- verified open-access papers acquired by the agent
- generated evidence matrices or other user-selected artifacts

Each chunk stores source path, source type, paper identity when available, public URL, acquisition time, and evidence scope. Query answers cite those source records and say when evidence is insufficient.

Public live acceptance data must have a provenance manifest. The project will not bundle confidential files or claim that an unlicensed standard or publisher PDF is freely redistributable.

## Workflow State and Visualization

### Event projection

Create a generic workflow-event projector over persisted session and turn events. It derives display nodes from real model calls, tool calls, approvals, pauses, interventions, rate limits, failures, and artifact creation.

It does not invent a domain sequence. A run that performs data analysis before literature retrieval is displayed in that actual order.

Each display node contains:

- stable event or operation identity
- tool or operation name
- state and timestamps
- truthful summary
- available metrics supplied by the tool result
- produced artifact references
- error, approval, pause, or intervention metadata

### Task summaries

The sessions API adds actual active-turn state, last meaningful event, artifact count, and workflow summary. Numeric progress is returned only when the runtime has a finite plan with a known total. Otherwise the UI uses an indeterminate current-step state.

An idle `active` session is displayed as ready or idle, never running. Waiting for approval is distinct from an ordinary paused intervention state.

### Persistence and recovery

Reloading the browser reconstructs the workflow trace from persisted events. Pause, intervention, approval, reconnect, cancellation, and restart must preserve already completed artifacts and event ordering.

## Workbench Design

### Visual direction

Preserve the current warm cream and sage foundation. Apply the supplied reference image as editorial art direction, not a copied screen:

- a high-contrast open-source serif for the Latin wordmark and selected display headings
- a compatible Chinese serif for major Chinese headings
- charcoal, cream, and muted olive accents
- restrained line motifs and subtle grain in brand or hero surfaces
- strong typographic scale and deliberate whitespace

Keep the task workspace light and readable. Do not turn every page into a dark poster. Retain the `Research Agent` product name unless the user separately requests a rename.

### Interaction changes

- Add a collapsible persisted workflow trace to the workspace.
- Add generic artifact inspectors for paper pools, evidence matrices, analysis results, images, reference audits, and text files based on artifact types.
- Show literature round counts and stop reasons from tool data.
- Show statistics, warnings, and anomaly counts in a table-oriented result view.
- Show before/after reference entries and unresolved metadata.
- Remove fixed task percentages and repair idle/running classification.
- Display actual result and artifact summaries in the task center.
- Preserve upload, plan, pause, intervention, approval, scheduling, settings, and general chat behavior.
- Fix medium-width navigation clipping and dense task layouts found during browser inspection.

The workbench continues to use React and the existing CSS stack. New visual dependencies are allowed only when necessary, locally stored when practical, licensed, and recorded.

## Error and Recovery States

- A single failed literature source leaves other source results usable.
- Invalid semantic-evaluator output is retried through the model gateway policy, then reported as incomplete without lexical fallback.
- Missing abstracts or full text remain explicit evidence gaps.
- Unsupported data columns or insufficient observations produce structured warnings or errors, not silent coercion.
- A chart failure does not invalidate a successful statistical report.
- Metadata enrichment failure leaves the original reference and an unresolved audit entry.
- Workflow trace rendering failure does not block the conversation or artifacts.
- A stale backend is rejected by runtime version and route compatibility checks.
- SQLite and session-store connections are closed explicitly in application and test lifecycles.

## Verification Strategy

### Focused tests

- semantic literature decisions are consumed from structured model output rather than local aliases or weights
- model evaluation failure produces an incomplete raw pool instead of a guessed screened pool
- explicit year, venue, source, and exclusion constraints remain deterministic
- extraction failure never guesses method, innovation, findings, or conclusion
- data roles and methods come from an explicit analysis specification
- chart arguments cannot be overridden by request text
- reference enrichment retains provenance and never overwrites source values silently
- idle sessions are not reported as running
- unknown progress remains indeterminate
- persisted events rebuild the same workflow trace after reload
- pause, intervention, approval, and cancellation remain distinct

### Integration tests

- multi-source search with mocked adapters and semantic evaluator
- search through evidence matrix to grounded review outline
- upload through statistics, anomaly flags, and real chart files
- reference import through enrichment, audit, multi-style output, and DOCX preservation
- RAG answer with source citations and explicit insufficient-evidence behavior
- frontend rendering for every typed artifact and workflow state

### Full and live acceptance

After implementation:

1. Run all backend tests.
2. Run all frontend tests and the production build.
3. Start the actual workbench through `start_workbench.ps1` and verify runtime version, routes, and port ownership.
4. Run a real public multi-source literature task and retain the round trace and paper pool.
5. Generate a real evidence matrix and review outline from that pool.
6. Download or use a small public tabular dataset with provenance, upload it through the browser, and retain the statistics, anomaly output, and chart files.
7. Format and audit a real reference fixture in GB/T 7714 and at least one alternate style.
8. Pause an active task, submit a correction, continue the same turn, reload, and verify the trace remains visible.
9. Inspect desktop and narrow viewport layouts in a real browser.
10. Perform a hard-coding audit of planner-visible handlers and frontend behavior.

Network-dependent acceptance records source availability and does not convert an external outage into a false success.

## Hard-coding Audit Standard

The final audit searches active planner-visible paths for:

- regex or substring routing on free-form user requests
- domain synonym tables used as semantic truth
- fixed relevance weights or query-expansion counts
- canned semantic extraction fallbacks
- fake progress, price, count, or result values
- mandatory academic tool sequences

Findings are classified as:

- prohibited semantic or presentation hard-coding
- acceptable deterministic standard, parser, schema, safety, or capability rule
- isolated legacy code that is not imported by the current runtime

Prohibited findings in changed or active academic paths must be fixed before completion. Isolated legacy modules are reported honestly and left untouched unless their removal is required for runtime correctness.

## Delivery Slices

1. Truthful session summaries and persisted workflow projection.
2. Model-driven recursive literature evaluation and removal of lexical semantic fallbacks.
3. Strict evidence extraction and grounded review artifacts.
4. Schema-first data analysis with explicit chart specifications.
5. Reference enrichment, provenance audit, and output comparison.
6. RAG provenance manifest and typed artifact inspection.
7. Editorial visual upgrade and responsive workflow/result surfaces.
8. Full regression, public-data live demonstrations, browser inspection, and hard-coding audit.

Each slice must preserve all previously working general-agent capabilities and leave an inspectable artifact or user-visible behavior.

## Completion Criteria

The work is complete only when the four required academic functions and the intervention/workflow requirement can each be demonstrated through the real browser workbench with persisted, inspectable outputs; the full automated suites and production build pass; public-source and uploaded-data smoke tasks produce real artifacts; task status and progress are truthful; and the active runtime contains no keyword router, fixed academic workflow, semantic regex fallback, or fabricated UI values.
