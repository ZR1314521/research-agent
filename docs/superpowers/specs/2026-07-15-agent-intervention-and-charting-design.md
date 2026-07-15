# Agent Intervention and Scientific Charting Design

## Goal

Add two user-visible capabilities to the local Research Agent without introducing keyword routing or a fixed research workflow:

1. Generate real scientific charts from uploaded tabular data and expose the resulting files to the user.
2. Let the user pause an active turn, provide a correction or additional instruction, and continue in the same run with its conversation and artifacts intact.

The implementation must preserve the current model-led runtime. The model decides whether to use a tool, which tool to use, and how to combine tools. Application code is limited to tool execution, input validation, permissions, persistence, cancellation, and truthful result delivery.

## Non-goals

- No keyword-to-chart mapping.
- No hard-coded sequence such as search, screen, summarize, then chart.
- No mandatory pause at a specific research step.
- No general-purpose online editor for CSV, JSON, Markdown, DOCX, or PDF in this version.
- No image-generation model or decorative text-to-image feature.
- No automatic replacement of an existing user file.
- No rewind or arbitrary historical checkpoint restoration in this version.

## Chosen Approach

Use a generic intervention layer over the existing conversation and turn-control runtime, plus a generic chart-rendering tool exposed through the existing skill registry.

Two alternatives were rejected:

- A fixed research workflow with predefined pause nodes would be easier to demonstrate but would violate the model-led and no-hard-coding constraint.
- A browser editor for every artifact type would expand the scope substantially and would not improve the first version's core pause-correct-continue loop.

## Charting Architecture

### Tool contract

Register a planner-visible chart tool with a neutral contract. Its inputs describe rendering intent rather than user intent:

- source file or current dataset artifact
- chart type
- x, y, grouping, and optional value columns
- title and axis labels
- output format
- optional presentation settings that are safe and bounded

The initial supported chart operations are line, scatter, bar, histogram, box, and heatmap. This is an executable capability list, not semantic routing. The model chooses an operation by calling the tool with explicit arguments.

### Renderer

The renderer reads CSV, TSV, TXT, XLSX, or XLSM through the existing tabular-data boundary. It validates that requested fields exist, converts usable values, and uses matplotlib to create a real PNG. SVG is also supported when requested.

Every result includes:

- the output image path
- the source dataset path
- chart type and selected columns
- warnings about dropped or unusable values
- a structured artifact record for the workbench

Output names are unique within the run so a new chart does not silently overwrite an earlier result.

### Dependency

Add matplotlib to `requirements-local.txt` and install it only in the project `.venv`. Do not modify the system Python environment.

## Artifact Presentation

The workbench treats artifacts generically. It may use the artifact media type or file extension to decide whether an inline preview is available; it must not use research-domain keywords.

For a PNG or SVG artifact:

- show an inline preview when the browser can load it safely
- keep the file name and path visible
- allow the user to open the full artifact

If previewing fails, the artifact remains successful and the UI displays its full path. The charting acceptance criterion is therefore: preview when possible, path always.

Other artifact types continue to use the existing artifact presentation. This version does not add an editor.

## Intervention Architecture

### Pause boundary

Reuse the existing turn coordinator. A pause request stops the agent only at a safe boundary between model or tool operations. An already-running atomic tool is allowed to finish or return its normal cancellation result; application code must not corrupt a partially written artifact to simulate an immediate pause.

The paused run preserves:

- the same run identifier
- native model messages and tool observations
- current artifacts and artifact records
- the last completed event sequence
- pending approval state, when applicable

### Continue with a correction

While paused, the user may enter an ordinary natural-language instruction. The backend appends that instruction to the same conversation and starts a continuation turn. The model sees the preserved context and current artifact ledger, then independently chooses whether to reuse artifacts, call another tool, or answer directly.

No code path interprets phrases such as "exclude reviews", "use 3 sigma", or "make a box plot". Those semantic decisions remain with the configured model.

The user may also continue without adding a correction. That resumes normal execution from the safe boundary.

### Approval remains separate

Pause and approval are different states:

- Pause is user-initiated course correction.
- Approval is a runtime request before a side effect covered by the permission policy.

The UI must not merge these states or show Allow/Reject for an ordinary pause.

## Workbench Interaction

Keep the current Pause, Resume, and Cancel controls. When a run is paused:

- the composer remains available
- its helper text explains that the next message adjusts the current task
- sending a message continues the same run with that message
- a separate Continue action resumes without a new message

The activity view continues to show tool progress and artifacts. Chart artifacts appear in the same result area as other artifacts, with inline preview when available and an explicit path fallback.

No chart-specific or research-stage-specific button is required. Users request charts and corrections in natural language.

## Error Handling

- Unsupported chart types or missing columns return a structured tool error to the model and user.
- Invalid values are reported; they are not silently fabricated or coerced into misleading results.
- Chart rendering failure does not remove the source dataset, analysis report, or earlier artifacts.
- A preview failure does not mark a successfully generated chart as failed.
- Resume requests for a run that is not paused return a clear conflict response.
- A correction submitted after cancellation starts no hidden background continuation.
- Successful chart paths are verified to exist before being registered as artifacts.

## Testing and Acceptance

### Backend

- The chart tool is present in the data-driven skill registry and callable through the normal model/tool loop.
- CSV and XLSX fixtures can generate non-empty PNG output.
- Requested SVG output is valid and non-empty.
- Missing columns and unsupported chart operations fail truthfully.
- Source data is unchanged after chart generation.
- Pause reaches a safe boundary and preserves the run.
- A correction continues the same run and is present in the native conversation history.
- Continue-without-correction works.
- Approval and pause states remain distinct.

### Frontend

- Paused state keeps the composer usable and labels it as a task adjustment.
- Sending an adjustment continues the current run rather than creating a new run.
- Continue-without-adjustment calls the resume control.
- PNG and SVG artifacts render a preview when accessible.
- Every chart artifact displays a file path even when previewing fails.

### Regression and smoke checks

- Existing backend and frontend suites continue to pass.
- A real browser smoke test covers upload data, request analysis and a chart, inspect the preview or path, pause, submit a correction, and continue.
- No test relies on keyword routing or a fixed sequence of research tools.

## Completion Criteria

The feature is complete when a user can upload tabular data, ask naturally for an analysis or visualization, receive a real chart file, see that chart or its path in the workbench, pause the same task, provide a correction, and continue without losing conversation context or artifacts. Inspection of the implementation must show no keyword router and no mandatory research workflow added for these behaviors.
