# Model-selected search routes and theme types

## Goal

Keep the existing model-led agent loop and theme system while making search outcomes truthful, exposing search routes as peer capabilities, and adding an extensible visual `Type` layer to the palette.

## Search contract

- OpenCLI web search, direct HTTP web search, OpenAlex, Semantic Scholar, Crossref, PubMed, and arXiv are peer tools visible to the model.
- No service silently selects a source or tries providers in a fixed fallback order. A multi-source request must name its sources; OpenCLI must name its adapter; direct HTTP search must name its provider.
- Every successful tool return carries one outcome: `success`, `empty`, `partial`, `rate_limited`, `failed`, or `cancelled`.
- The agent loop projects that outcome to the event stream and UI instead of treating every returned dictionary as successful.
- Resource guards may reject an identical repeated call or require batched inputs, but they do not select the next route.

## User-facing behavior

- Only `success` is a normal green completion. `partial`, `empty`, `rate_limited`, `failed`, and `cancelled` have distinct states and plain-language summaries.
- The model still receives tool observations and writes the final natural-language answer. JSON, raw logs, and internal artifacts do not become the final response.
- Cancelling a turn finalizes queued/running projected steps immediately.

## Theme type

- Theme colors and visual type are independent. Selecting `像素实验室` retains all current colors and later color edits continue to apply.
- The palette contains a standalone `Type` block with `标准界面` and `像素实验室`. The schema stores a semantic type value, so more types can be added later without checking preset names.
- Pixel type uses local fonts, square block surfaces, hard offset shadows, crisp borders, and color-token-based pixel patterns. It does not pixelate research images or charts.

## Verification

- Unit tests cover missing source selection, rate limits, partial/empty outcomes, Crossref search, explicit OpenCLI/HTTP provider selection, cancellation projection, theme persistence, and live color changes in pixel type.
- Full backend tests, frontend tests, and production build must pass.
- Final review searches for hidden source defaults, ordered fallbacks, forced next-tool fields, stale running steps, raw structured output leakage, and unbounded repeated calls.
