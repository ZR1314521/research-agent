# Workbench Theme and Output Integrity Design

**Date:** 2026-07-16  
**Status:** Approved

## Goal

Make the local research workbench visually configurable and operationally honest without removing existing general-agent capabilities. The implementation must prevent internal structured model output from leaking into user chat, expose real task budgets and workflow state, and make every supported theme control affect the full interface.

## Product decisions

- Build a safe theme studio, not an arbitrary CSS editor or drag-and-drop DOM builder.
- Keep one semantic theme schema as the source of truth for colors, typography, geometry, density, layout, effects, and navigation behavior.
- Treat configured defaults as configuration, while removing duplicated literals and component-level visual constants.
- Keep internal tool/model protocol data separate from user-visible assistant output.
- Display only persisted or currently observed workflow steps and artifacts; never invent progress.

## Theme architecture

The theme schema contains versioned sections for:

- `colors`: page, surface, elevated surface, soft surface, primary text, secondary text, accent, accent strong, border, success, warning, danger.
- `typography`: display family, body family, monospace family, base scale.
- `shape`: control radius, card radius, panel radius.
- `layout`: content width, sidebar width, interface density.
- `effects`: shadow strength and background mode (`solid`, `grain`, `gradient`).
- `navigation`: auto-hide enabled and motion enabled.

A single adapter applies the schema to CSS custom properties. Components consume semantic properties only. Existing saved palettes are migrated to the current schema. Users can preview, reset, import, and export JSON configurations. Invalid imported values are rejected with a readable message and do not partially mutate the active theme.

The fixed white radial glow is removed. Background effects use theme-derived colors and can be disabled.

## Navigation behavior

Every page uses the same top navigation component. It remains fixed at the top, hides after deliberate downward scrolling, reappears on upward scrolling, and is always visible near the top of the page. Direction detection uses a named interaction configuration with hysteresis to avoid jitter. Reduced-motion preferences disable animated transitions.

## User-visible model output

Provider events gain an explicit visibility boundary:

- Main agent response deltas are user-visible and may stream into chat.
- Internal tool/model calls may report lifecycle and usage events, but their response, reasoning, tool-call, and structured-data deltas are not user-visible.
- Final internal JSON remains available to the capability that requested it and to diagnostics, but never appears in a chat bubble.

This fixes the observed literature-screening JSON leak at the event layer rather than relying on prompts or content filtering.

## Budgets, workflow steps, and artifacts

Run budgets come from one backend configuration object and are included in run payloads. The UI does not own independent default limits. Settings expose supported per-turn call and token limits with validation and source labeling.

Workflow steps are built from real lifecycle events. Long academic tools may publish meaningful subphases such as search, semantic screening, and result preparation. Cancellation preserves completed/failed/cancelled states. Artifacts are displayed only after registration; artifacts completed before cancellation should remain accessible when registration has succeeded.

## Verification

Verification focuses on user outcomes rather than cosmetic refactoring:

- Backend tests for event visibility, budget configuration, lifecycle persistence, cancellation, and artifact payloads.
- Frontend tests for theme migration, validation, persistence, import/export, all token applications, and navigation direction behavior.
- Production frontend build and backend suite.
- A real EEG-MI request smoke test proving no internal JSON/code protocol appears in chat.
- Manual theme checks across every page, refresh persistence, and each background mode.
- Targeted scans for duplicated budget literals, component-level fixed theme colors, and internal event forwarding.

The hard-code review distinguishes legitimate centralized defaults and UI copy from duplicated behavior rules or values that should be configuration-driven.
