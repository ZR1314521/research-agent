# Session Switch Race Fix

## Outcome

Selecting a conversation is a user-owned action. Late responses, stream events, refreshes, and reconnects from a previously selected conversation must never change the currently selected conversation or render into it. A running conversation continues on the backend when the user views or creates another conversation, and reconnects when selected again.

## Scope

- Fix the single-window, multi-conversation workbench behavior.
- Preserve shared behavior when two windows deliberately open the same run ID.
- Allow free navigation while another conversation is running.
- Do not change layout, backend session storage, or task execution semantics.

## Design

`runId` remains the selected conversation, but only explicit navigation and successful run creation may change it. Applying fetched run data must not implicitly select that run.

Each asynchronous operation captures both the requested run ID and the current UI generation. Before applying data or events, it checks that both still match the active selection. A stale operation may finish in the background, but its result is ignored by the current view.

Session switching increments the generation before starting the new fetch, clears view-local state, and performs one detail refresh. Duplicate refreshes caused by both the switch handler and the `runId` effect are removed.

The backend `TurnCoordinator` owns task lifetime. Leaving a conversation aborts only that browser view's stream reader; it does not call the run cancellation endpoint. Creating a new conversation follows the same rule.

When a selected run reports an active turn, the workbench reconnects through `/runs/{run_id}/turns/{turn_id}/events`. It replays that turn's events into a fresh streaming assistant entry and then follows new events until a terminal or approval boundary. If the turn completed while hidden, the ordinary run refresh supplies the persisted final answer instead.

Only the selected run has a browser event connection. The design does not maintain parallel UI streams or per-domain routing. Ownership is determined generically from `run_id`, `turn_id`, UI generation, and event sequence.

## Failure handling

- A stale request is silently ignored; it is not a user-visible error.
- A current request failure may show an error but cannot change the selected run.
- Starting a new run adopts the returned run ID explicitly.
- Navigating away never cancels backend work; explicit Cancel remains the only cancellation action.
- Reconnection failure leaves the backend task intact and exposes a recoverable view error.
- Opening the same run ID in another window continues to show shared backend state by design.

## Verification

- Add a race regression where A is requested, the user selects B, B resolves, and A resolves last; B must remain selected and only B content may render.
- Add a background-navigation regression: start A, switch to B while A runs, complete A in the background, and switch back; A's final answer must be visible and B must never receive A events.
- Cover stale refresh, stale stream-event ownership, and selected-run reconnection.
- Run the frontend test suite and production build.
- Re-run the backend suite to prove the frontend-only fix did not disturb the runtime.

## Self-review

- No placeholders or unresolved choices.
- Current-run ownership is explicit.
- Same-run multi-window sharing is preserved.
- Background task lifetime is owned by the backend, not by the selected page.
- No keyword, tool-name, model-name, or fixed-time routing is introduced.
- No unrelated refactor or UI redesign is included.

## Verification results

- The regression reproduced the original race: after B rendered, A's late response changed the active heading back to A.
- With ownership guards in place, the same test keeps B selected and rejects A's stale content.
- A running A can be left for B without cancellation; returning after A completes shows its persisted final answer.
- Returning to an active A reconnects to its recorded turn, replays events, and does not retain B's messages.
- Creating a conversation while A runs does not call A's cancellation endpoint.
- Frontend: 9 tests passed across 4 suites.
- Production workbench build compiled successfully.
- Backend: 114 tests passed.
