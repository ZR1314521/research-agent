---
name: opencli-browser
description: Use when an agent needs to drive a real Chrome window via opencli — inspect a page, fill forms, click through logged-in flows, or extract data ad-hoc. Covers the selector-first target contract, compound form fields, stale-ref handling, network capture, and the agent-native envelopes the CLI returns. Not for writing adapters — see opencli-adapter-author for that. Triggers Data Extraction Patterns whenever: (1) curl/download returns 301/404/HTML instead of real files, (2) target data is in JS bundles not JSON APIs, (3) assets behind CDN anti-leech that only the browser can load. Triggers Design Replication whenever user says "一模一样" / "复刻" / "pixel-perfect" / "1:1 copy" — proactively asks to download CSS/JS/images/fonts/HTML for full source replication.
allowed-tools: Bash(opencli:*), Read, Edit, Write
---

# opencli-browser

The first reader of this CLI is an agent, not a human. Every subcommand returns a structured envelope that tells you exactly what matched, how confident the match is, and what to do if it didn't. Lean on those envelopes — do not guess.

This skill is for **driving a live browser** to accomplish an agent task. If you are building a reusable adapter under `~/.opencli/clis/<site>/` use `opencli-adapter-author` instead.

---

## Architecture (READ FIRST)

```
┌──────────┐   CLI    ┌──────────┐  WebSocket   ┌───────────────┐  chrome.debugger  ┌─────────┐
│  opencli  │─────────▶│  Daemon  │◀────────────▶│  Extension     │──────────────────▶│ Chrome  │
│  (shell)  │          │ :19825   │ ws://:19825  │  (background)  │   internal API    │  (tab)  │
└──────────┘          └──────────┘   /ext        └───────────────┘                  └─────────┘
```

**The extension connects to the daemon via WebSocket (`ws://localhost:19825/ext`). It uses Chrome's internal `chrome.debugger` API — `--remote-debugging-port=9222` is NOT needed and NOT used.**

If you don't believe this, read the extension's `background.js`: `DAEMON_WS_URL = ws://${DAEMON_HOST}:${DAEMON_PORT}/ext`. No port 9222 anywhere.

## Prerequisites

```bash
opencli doctor
```

Until `doctor` is green (all three: **Daemon ✓**, **Extension ✓**, **Connectivity ✓**), nothing else will work.

- **Daemon**: runs on port 19825. Start it with `opencli daemon start` if missing.
- **Extension**: must be installed in Chrome and Chrome must be running. The extension's popup will show connection status.
- **Connectivity**: the round-trip test — confirms the CLI → daemon → extension → Chrome pipeline works.

Typical failures:
- Extension not installed → install from [GitHub releases](https://github.com/jackwener/opencli/releases) or Chrome Web Store
- Chrome not running → just open Chrome normally
- Extension installed but Chrome was started with a **different profile** (e.g. `--user-data-dir`) that doesn't have the extension → use the user's normal Chrome
- Another extension (1Password, etc.) holding the debugger lock → temporarily disable it

---

## Session lifecycle

- `opencli browser *` commands require a `<session>` positional immediately after `browser`. Use the same session name for a multi-step flow; use a different name to isolate parallel browser work.
- Use a stable session name for any multi-command or human-paced browser workflow. Example: `opencli browser fb-yaya-warmup open https://example.com`, then reuse `opencli browser fb-yaya-warmup state`, `extract`, `click`, etc.
- Owned browser sessions keep a tab lease alive between calls. Release it with `opencli browser <session> close` or let the idle timeout expire.
- `opencli browser <session> bind` binds the Chrome tab you already have open to that session. Use this for logged-in pages, SSO flows, or pages you manually positioned before handing control to the agent.
- `--window foreground|background` (or `OPENCLI_WINDOW=foreground|background`) chooses whether OpenCLI creates/focuses a foreground browser window or uses a background browser window for owned sessions.

### Bind Tab

```bash
opencli browser gmail bind
opencli browser gmail state
opencli browser gmail click "Search"
opencli browser gmail network
opencli browser gmail unbind
```

Binding never owns the user window and never closes the user tab. It fails closed if the tab is closed or becomes non-debuggable. Re-run `opencli browser <session> bind` when you switch to a different real tab.

Navigation is allowed on bound sessions because the session now represents explicit agent ownership of that tab. Tab mutation (`tab new`, `tab select`, `tab close`) is still blocked for bound sessions. Use an owned session when you want OpenCLI to manage tab lifecycle.

Bound sessions have no OpenCLI idle-close timer; the binding lasts until `unbind`, tab close, window close, or daemon restart.

---

## Mental model

1. **Selector-first target contract.** Every interaction command (`click`, `type`, `select`, `get text/value/attributes`) takes one `<target>`, which is *either* a numeric ref from `state`/`find` *or* a CSS selector. Use `--nth <n>` to disambiguate multiple CSS matches.
2. **Every envelope reports `matches_n` and `match_level`.** `match_level` is `exact`, `stable`, or `reidentified` — the CLI already rescued moderate DOM drift for you, but the level tells you how confident to be.
3. **Compact output first, full payload on demand.** `state` is a budget-aware snapshot; `get html --as json` supports `--depth/--children-max/--text-max`; `network` returns shape previews and you re-fetch a single body with `--detail <key>`. If you emit a giant payload you are burning context you did not need to burn.
4. **Structured errors are machine-readable.** On failure the CLI emits `{error: {code, message, hint?, candidates?}}`. Branch on `code`, not on message strings.

---

## Critical rules

1. **Always inspect before you act.** Run `state` or `find` first. Never hard-code a ref or selector from memory across sessions — indices are per-snapshot.
2. **Prefer site adapters before raw browser driving.** If `opencli <site> <command>` already covers the task, use that adapter command first (`opencli facebook notifications`, `opencli reddit read`, etc.). Use `opencli browser ...` only for gaps, debugging, or one-off UI flows the adapter does not expose.
3. **Prefer numeric ref over CSS once you have it.** Numeric refs survive mild DOM shifts because the CLI fingerprints each tagged element. A CSS selector written by hand will break the first time the site re-renders.
4. **Read `match_level` after every write.** `exact` = all good. `stable` = the element is the same but some soft attrs drifted — your action still applied. `reidentified` = the original ref was gone and the CLI found a unique replacement; double-check you hit the right element.
5. **Use the `compound` field for form controls.** Do not regex-guess a date format, do not `state` twice to get the full `<select>` options list. The compound envelope has the format string, full option list up to 50, `options_total` for overflow, and `accept`/`multiple` for `<input type=file>`.
6. **Verify writes that matter.** After `type <target> <text>`, run `get value <target>`. After `select`, run `get value`. Autocomplete widgets, React controlled inputs, and masked fields all silently eat characters. The CLI cannot detect this for you.
7. **`state` → action → `state` after a page change.** Navigations, form submits, and SPA route changes invalidate refs. Take a fresh snapshot. Do not reuse refs from before the transition.
8. **Chain with `&&` when reusing freshly parsed refs.** A chained sequence runs in one shell so the ref you just read from output can be passed directly to the next command. Separate shell invocations keep the named browser session, but any shell-local variables or copied refs from the previous command can go stale after page changes.
9. **`eval` is read-only.** Wrap the JS in an IIFE and return JSON. If you need to *change* the page, use the structured `click` / `type` / `select` / `keys` commands instead — they produce structured output and fingerprints, `eval` does not.
10. **Prefer `network` to screen-scraping.** If a page you care about fetches its data from a JSON API, the API is almost always more reliable than scraping the rendered DOM. Capture once, inspect the shape, then `--detail <key>` the body you need.

---

## Sitemaps

If `browser open` or `browser analyze` returns `sitemap.available: true`, switch to `opencli-browser-sitemap` before continuing a multi-step site flow. The sitemap is prior context for pages, actions, workflows, APIs, and pitfalls; it is not truth. If the browser state disagrees with the sitemap, trust the browser and mark the sitemap stale via `opencli-sitemap-author`.

---

## Target contract (`<target>` for click / type / select / get text|value|attributes)

```
<target> ::= <numeric-ref> | <css-selector>
```

- **Numeric ref** — the `[N]` index from `state` or `find`. Cheap, resilient to soft DOM drift.
- **CSS selector** — anything `querySelectorAll` accepts. Must be unambiguous on write ops, or pair with `--nth <n>`.

### Envelope on success

```json
{ "clicked": true, "target": "3", "matches_n": 1, "match_level": "exact" }
```

```json
{ "value": "kalevin@example.com", "matches_n": 1, "match_level": "stable" }
```

### match_level

| level | meaning | you should |
|-------|---------|------------|
| `exact` | Fingerprint agreed on tag + strong IDs with at most one soft drift | Proceed. |
| `stable` | Tag + strong IDs still agree, soft signals (aria-label, role, text) drifted | Proceed, but if *what* you typed/clicked matters, re-check with `get value` or `state`. |
| `reidentified` | Original ref was gone; a unique live element matched the fingerprint and was re-tagged with the old ref | Double-check you hit the right element before chaining more writes. |

### Structured error codes

Branch on these, not on the human message:

| code | meaning |
|------|---------|
| `not_found` | Numeric ref is no longer in the DOM. Re-`state`. |
| `stale_ref` | Ref exists but the element at that ref changed identity. Re-`state`. |
| `invalid_selector` | CSS was rejected by `querySelectorAll`. Fix the selector. |
| `selector_not_found` | CSS matches 0 elements. Try `find` with a looser selector. |
| `selector_ambiguous` | CSS matches >1 and no `--nth`. Add `--nth` or narrow the selector. |
| `selector_nth_out_of_range` | `--nth` beyond match count. |
| `option_not_found` | `select` couldn't find an option matching that label/value. Error envelope includes `available: string[]` of the real option labels. |
| `not_a_select` | `select` was called on a non-`<select>` element. |

Error envelope always includes `error.code` and `error.message`. Target errors (`selector_not_found`, `selector_ambiguous`, etc.) often add `error.candidates: string[]` with suggested selectors. `option_not_found` adds `error.available: string[]` instead.

---

## Command reference

### Inspect

| command | purpose |
|---------|---------|
| `browser state` | Snapshot: text tree with `[N]` refs, scroll hints, hidden-interactive hints, `compounds (N):` sidecar for date/select/file refs. |
| `browser state --source ax` | Opt-in accessibility-tree snapshot. Use when custom controls, portals, or iframe contents are hard to identify in normal `state`. AX refs can recover stale React re-renders by role/name/nth and can route same-origin iframe refs. Cross-origin iframe refs are best-effort because Chrome may not expose attachable OOPIF targets to extensions. |
| `browser state --compare-sources` | Metrics-only DOM vs AX comparison for deciding whether AX should become default. It prints counts and sizes, not page text, so it is safer to share for validation. |
| `browser find --css <sel> [--limit N] [--text-max N]` | Run a CSS query and return one entry per match with `{nth, ref, tag, role, text, attrs, visible, compound?}`. Allocates refs for matches the prior snapshot didn't tag. Cheap alternative to `state` when you already know the selector. |
| `browser find --role button --name Save` | Semantic locator query. Also supports `--label`, `--text`, and `--testid`. Use before raw CSS when a control has accessible labels. |
| `browser frames` | List cross-origin iframe targets. Pass the index to `--frame` on `eval`. |
| `browser screenshot [path]` | Viewport PNG. No path → base64 to stdout. Prefer `state` when you just need structure. |
| `browser screenshot --annotate [path]` | Visual ref map. Refreshes DOM refs and overlays visible `[N]` labels so the screenshot maps back to `browser click <ref>` targets. Use for icon-only controls, visual layouts, charts, or when text state is ambiguous. |

### Get (read-only)

| command | returns |
|---------|---------|
| `browser get title` | plain text |
| `browser get url` | plain text |
| `browser get text <target> [--nth N]` | `{value, matches_n, match_level}` |
| `browser get value <target> [--nth N]` | `{value, matches_n, match_level}` |
| `browser get attributes <target> [--nth N]` | `{value: {attr: val, ...}, matches_n, match_level}` |
| `browser get text --role option --name Travel` | Semantic locator read without a prior `state` call. Same flags as `browser find`. |
| `browser get html [--selector <css>] [--as html\|json] [--depth N] [--children-max N] [--text-max N] [--max N]` | Raw HTML, or structured tree. JSON tree nodes have `{tag, attrs, text, children[], compound?}`. Truncation reported via `truncated: {depth?, children_dropped?, text_truncated?}`. |

### Interact

| command | notes |
|---------|-------|
| `browser click <target> [--nth N]` | Returns `{clicked, target, matches_n, match_level}`. |
| `browser click --role button --name Submit` | Semantic click. Write actions require a unique match; ambiguous locators return candidates instead of clicking the first match. |
| `browser hover [target] [--role R --name N] [--nth N]` | Moves the mouse over an element. Use for hover menus/tooltips before taking `state` or clicking submenu items. Returns `{hovered, target, matches_n, match_level}`. |
| `browser focus [target] [--role R --name N] [--nth N]` | Focuses an element without typing. Useful before `keys` or when a page reacts to focus/blur. Returns `{focused, target, matches_n, match_level}`. |
| `browser dblclick [target] [--role R --name N] [--nth N]` | Double-clicks an element via native mouse events when available. Returns `{dblclicked, target, matches_n, match_level}`. |
| `browser check [target] [--role R --name N] [--nth N]` | Ensures checkbox/radio/aria-checked control is checked. Returns `{checked, changed, target, matches_n, match_level, kind}`. Prefer this over blind `click` when target state matters. |
| `browser uncheck [target] [--role R --name N] [--nth N]` | Ensures checkbox/aria-checked control is unchecked. Radio buttons cannot be unchecked directly; select another radio in the group instead. |
| `browser upload [target] <file...> [--role R --name N] [--nth N]` | Attaches local file path(s) to an `input[type=file]` via CDP. With semantic flags, omit `target` and pass files as positionals. Returns `{uploaded, files, file_names, target, matches_n, match_level, multiple?, accept?}`. |
| `browser drag [source] [target] [--from-role R --from-name N] [--to-role R --to-name N] [--from-nth N] [--to-nth N]` | Mouse-based drag from one resolved element center to another. Works for mouse-listener drag libraries; native HTML5 `dataTransfer` drops may need a site-specific fallback. Returns `{dragged, source, target, source_matches_n, target_matches_n, ...}`. |
| `browser type [target] <text> [--role R --name N] [--nth N]` | Clicks first, then types. With semantic flags, omit `target` and pass text as the only positional. Returns `{typed, text, target, matches_n, match_level, autocomplete}`. `autocomplete: true` means a combobox/datalist popup appeared after typing — you almost always need `keys Enter` or a follow-up `click` on the suggestion to commit the value. |
| `browser fill [target] <text> [--role R --name N] [--nth N]` | Exact replacement for input, textarea, and contenteditable targets. With semantic flags, omit `target` and pass text as the only positional. Returns `{filled, verified, text, actual, matches_n, match_level}`. Use this when you need raw text set and verified, not keyboard/autocomplete behavior. Pipeline form supports `{ fill: { ref, text, submit: true } }`. |
| `browser select [target] <option> [--role R --name N] [--nth N]` | Matches native `<select>` option by label first, then value. With semantic flags, omit `target` and pass option as the only positional. Use `compound` from `find`/`state` to see exactly what labels are available. |
| `browser keys <key>` | `Enter`, `Escape`, `Tab`, `Control+a`, etc. Runs against the focused element. |
| `browser scroll <direction> [--amount px]` | `up` / `down`. Default amount `500`. |

### Wait

```bash
browser wait selector "<css>" [--timeout ms]    # wait until the selector matches
browser wait text "<substring>" [--timeout ms]  # wait until the text appears
browser wait download [pattern] [--timeout ms]  # wait for a Chrome download whose filename/URL/mime contains pattern
browser wait time <seconds>                     # hard sleep, last resort
```

Default timeout `10000` ms. SPA routes, login redirects, and lazy-loaded lists need `wait` before `state`/`get`.

`browser wait download` requires Browser Bridge extension 1.0.8+ because it uses
Chrome's downloads lifecycle API. Pass a narrow filename or URL substring such
as `receipt.pdf` when possible; an empty pattern waits for the next/recent
download in the timeout window. The command reports `{downloaded, filename, url,
state, elapsedMs}` on success and a JSON error envelope on timeout/failure.

### Extract

- **`web read --url <url>`** — One-shot Markdown reader for arbitrary pages. It expands relevant same-origin iframes by default, so old iframe-shell sites work better than with a top-document-only scrape. Use `--frames all-same-origin` when completeness matters more than Markdown noise. For AJAX shell pages use `opencli web read --url <url> --wait-for "<selector>" --wait-until networkidle --diagnose`; diagnostics show frame URLs, empty containers, and API-like XHRs. If the value you need is table/API data, switch to `browser network` or a dedicated adapter instead of relying on Markdown.
- **`browser eval <js> [--frame N]`** — Run an expression in the page (or in a cross-origin frame via `--frame`). Wrap in an IIFE and return JSON. Read-only: no `document.forms[0].submit()`, no clicks, no navigations. If the result is a string, stdout is the raw string; otherwise it's JSON.
- **`browser extract [--selector <css>] [--chunk-size N] [--start N]`** — Markdown extraction of long-form content with a continuation cursor. Returns `{url, title, selector, total_chars, chunk_size, start, end, next_start_char, content}`. Loop on `next_start_char` until it is `null`. Auto-scopes to `<main>`/`<article>`/`<body>` if you don't pass `--selector`.

### Network

```bash
browser network                        # shape preview + cache key list
browser network --detail <key>         # full body for one cached entry
browser network --filter "field1,field2"  # keep only entries whose body shape contains ALL fields as path segments
browser network --all                  # include static resources (usually noise)
browser network --raw                  # full bodies inline — large; use sparingly
browser network --ttl <ms>             # cache TTL (default 24h)
```

List entries look like `{key, method, status, url, ct, size, shape, body_truncated?}`. Detail envelope is `{key, url, method, status, ct, size, shape, body, body_truncated?, body_full_size?, body_truncation_reason}`. Cache lives in `~/.opencli/cache/browser-network/` so you can re-inspect without re-triggering the request.

Default output keeps JSON/XML/plain-text and JS-like API responses, then drops obvious static assets and telemetry by URL. If an expected endpoint is missing, run `browser network --all` once and check whether an unusual content type or URL filter hid it.

### Tabs & session

| command | purpose |
|---------|---------|
| `browser tab list` | JSON array of `{index, page, url, title, active}`. The `page` string is the tab identity you pass as `<targetId>` to `tab select` / `tab close`, or to `--tab <targetId>` on any subcommand. (`--tab`'s placeholder is historical — the value is always `page`.) |
| `browser tab new [url]` | Open a new tab. Prints the new `page` string. |
| `browser tab select [targetId]` | Make a tab the default. All subcommands accept `--tab <targetId>` to target one without changing the default. |
| `browser tab close [targetId]` | Close by `page`. |
| `browser back` | History back on the active tab. |
| `browser close` | Release the current owned browser session when done. |
| `browser <session> bind` | Bind the current Chrome tab to the named browser session. |
| `browser <session> unbind` | Detach the named bound session without closing the user tab/window. |

---

## Compound form controls

Every date/time, select, and file input carries a `compound` field. Use it — do not regex attributes.

### Date family

```json
{
  "control": "date",
  "format": "YYYY-MM-DD",
  "current": "2026-04-21",
  "min": "2026-01-01",
  "max": "2026-12-31"
}
```

`control` is one of `date | time | datetime-local | month | week`. `format` is a concrete template string — type into the field using that exact format, or `select` by label if the site wraps the native input in a custom widget.

### Select

```json
{
  "control": "select",
  "multiple": false,
  "current": "United States",
  "options": [
    { "label": "United States", "value": "us", "selected": true },
    { "label": "Canada", "value": "ca" }
  ],
  "options_total": 137
}
```

`options[]` is capped at 50 entries. **`current` is always correct** even when the selected option is past the cap — it's computed by scanning every option, not from the truncated list. If `options_total > options.length` and you need an option that isn't in `options[]`, call `browser select <target> "<label>"` directly — the CLI matches against the live DOM, not the truncated list.

### File

```json
{
  "control": "file",
  "multiple": true,
  "current": ["report.pdf", "cover.png"],
  "accept": "application/pdf,image/*"
}
```

Do not invent file paths. Upload is done via the normal click flow — respect `accept` when telling the user what to upload.

### Where compounds show up

- `browser find --css <sel>` entries: inline on each match.
- `browser get html --as json` tree nodes: inline on matching nodes.
- `browser state` snapshot: in a `compounds (N):` sidecar keyed by numeric ref, so you can tell at a glance which `[N]` entries have rich metadata.

---

## Cost guide

Think about payload size per call. Budgets exist for a reason.

| command | rough cost | when to use |
|---------|-----------|-------------|
| `state` | medium (bounded by internal budget) | First call on any page, after every nav, when you need refs. |
| `find --css <sel>` | small | You already know the selector — one query, compact entries. |
| `get title` / `get url` | tiny | Sanity checks between steps. |
| `get text/value/attributes` | tiny per call | Verifying one specific field. |
| `get html` (raw) | can be huge | Avoid on unbounded pages. Always pair with `--selector` and a budget. |
| `get html --as json --depth 3 --children-max 20` | medium | When you need to reason about structure, not a specific field. |
| `screenshot` | large | Only when the page is visual (CAPTCHA, charts). Prefer `state`. |
| `extract` | medium per chunk | Long-form reading. Loop via `next_start_char`. |
| `network` (default) | small | First look at APIs. |
| `network --detail <key>` | varies | Pull one body. |
| `network --raw` | huge | Only after `--filter` narrowed the candidate set. |
| `eval "JSON.stringify(...)"` | controlled | Targeted extraction when none of the above fit. |

Rule of thumb: **one `state` per page transition, one `find` per follow-up query, one `get`/`click`/`type` per action.** If your plan involves >10 calls per page you are probably scraping instead of interacting — consider `extract` or `network`.

---

## Chaining rules

**Good — one shell, live session:**

```bash
opencli browser hn open "https://news.ycombinator.com" \
  && opencli browser hn state \
  && opencli browser hn click 3
```

**Bad — each line is a fresh shell, refs from call 1 are already forgotten when call 2 runs.** (Only a problem if you rely on shell-scoped state; browser refs themselves persist in-page, but interleaving unrelated shells invites races.) Prefer `&&` when the steps are meant to be atomic.

**Never** chain a write and then an immediate `state` without a `wait` if the action causes a network round-trip — you will snapshot the pre-response DOM and make bad decisions off stale data.

---

## Recipes

### Fill a login form

```bash
opencli browser login open "https://example.com/login"
opencli browser login state                          # find [N] for email, password, submit
opencli browser login type 4 "me@example.com"
opencli browser login type 5 "hunter2"
opencli browser login get value 4                    # verify (autocomplete can eat chars)
opencli browser login click 6                        # submit
opencli browser login wait selector "[data-testid=account-menu]" --timeout 15000
opencli browser login state                          # fresh refs on the logged-in page
```

### Pick from a long dropdown

```bash
opencli browser form state                          # sidebar shows [12] <select name=country>
opencli browser form find --css "select[name=country]"
# the compound.options_total is 137, but compound.current is "" — unselected.
opencli browser form select 12 "Uruguay"
opencli browser form get value 12                   # { value: "uy", match_level: "exact" }
```

### Pick from a custom React dropdown

Use this for Radix, shadcn, Material UI, Mercury-style category fields, and
other controls that are not native `<select>`.

```bash
opencli browser mercury state                          # find category trigger ref
# If the trigger/option is not clear, use AX:
opencli browser mercury state --source ax              # look for combobox/button/listbox/option names
opencli browser mercury click 7                        # click category trigger
opencli browser mercury state --source ax              # fresh refs after the portal/listbox opens
opencli browser mercury click 12                       # click option
opencli browser mercury get text 7                     # verify visible selected label
```

Do not use `browser select` on these widgets. `browser select` is only for
native `<select>` elements. Custom dropdowns should be driven with
`state -> click trigger -> state -> click option -> verify`.

### Compare DOM vs AX observation

When deciding whether AX refs are better for a page, collect metrics without
sharing page contents:

```bash
opencli browser compare state --compare-sources
```

Report `sources.dom.refs`, `sources.ax.refs`, `frame_sections`,
`approx_tokens`, `elapsed_ms`, and any per-source `error`. Use this before
arguing that AX should become the default on a site.

### Scrape a list via network instead of DOM

```bash
opencli browser hn open "https://news.ycombinator.com"
opencli browser hn network --filter "title,score"
# -> find the /topstories entry, note its key
opencli browser hn network --detail topstories-a1b2
```

### Read a long article in chunks

```bash
opencli browser article open "https://blog.example.com/long-post"
opencli browser article extract --chunk-size 8000
# -> content + next_start_char: 8000
opencli browser article extract --start 8000 --chunk-size 8000
# ...until next_start_char is null
```

### Cross-origin iframe

```bash
opencli browser checkout frames
# -> [{"index": 0, "url": "https://checkout.stripe.com/...", ...}]
opencli browser checkout eval "(() => document.querySelector('input[name=cardnumber]')?.value)()" --frame 0
```

`browser state --source ax` may omit cross-origin iframe contents or fail to
route actions into them when Chrome does not expose an attachable OOPIF target
to the extension. In that case use `browser frames` + `browser eval --frame`, a
normal DOM `state`, or navigate/bind directly to the iframe URL when possible.

---

## Pitfalls

- **Do NOT kill the user's Chrome and launch a new instance with a different profile.** The new profile won't have the extension. You'll break their session, lose their tabs, and waste time. Chrome must run with the profile that has the OpenCLI extension installed.
- **Do NOT add `--remote-debugging-port=9222` to Chrome.** The extension uses `chrome.debugger` internal API and connects to the daemon via WebSocket — port 9222 is irrelevant. Adding this flag also causes Chrome to reject the default user-data-dir, leading to pointless profile workarounds.
- **Do NOT create "Chrome-OpenCLI" shortcuts or custom launchers.** The user just needs to open Chrome normally. The only prerequisite is that the extension is installed.
- **Do not submit forms via `eval "document.forms[0].submit()"`** — modern sites intercept with JS handlers and silently drop the call. Either `click` the submit button via its ref, or (if you know the GET URL) just `open` it directly.
- **Do not reuse refs across a page transition.** `wait` for the new state, then re-`state`. Old refs will either 404 or (worse) `reidentify` onto a similarly-shaped element on the new page.
- **`match_level: reidentified` is a warning, not an error.** The action went through, but if you are chaining 5 more writes that all depend on that being the right element, verify with a `get text` or `get value` before continuing.
- **Budget-aware commands silently cap.** `get html --as json` with default budgets will return `truncated: {...}`. If your downstream logic needs the whole subtree, raise `--depth` / `--children-max` or tighten the selector.
- **`autocomplete: true` on a `type` response is not an error.** It means a suggestion popup is open and your value isn't committed yet. Typically `keys Enter` to accept the first suggestion, or `click` the one you want.
- **`network --filter` is AND-semantics on path segments.** `--filter "title,score"` keeps entries whose body shape contains *both* `title` and `score` as path segments, at any depth. It is not a regex.
- **Screenshots are for humans, not for agents.** Use `state` + `find` unless the page is genuinely visual (captcha, chart). Screenshots burn tokens and rarely add signal an agent can act on.

---

## Troubleshooting

| symptom | fix |
|---------|-----|
| `opencli doctor` red: "Extension: not connected" | Chrome is not running, or the extension is not installed in this Chrome profile. Just open Chrome normally (no special flags). If extension is missing, install from [GitHub releases](https://github.com/jackwener/opencli/releases). Do NOT add `--remote-debugging-port` — it's not required and breaks default-profile Chrome. |
| `attach failed: chrome-extension://...` | Disable 1Password / other CDP-hungry extensions temporarily. |
| `selector_not_found` right after `state` | Page mutated. `wait selector "..."` then retry. |
| `stale_ref` across every command | You are reusing refs from a prior page. Re-`state`. |
| `click` succeeds but nothing happens | The element is probably a decorative wrapper stealing clicks from the real target. `find --css "..."` with a narrower selector and retry on the inner element. |
| `type` appears to finish but value is wrong | Autocomplete, masked input, or React controlled re-render. Verify with `get value`. Add `keys Enter` or re-type. |
| Giant `get html` output | Pass `--selector` + `--as json --depth 3 --children-max 20 --text-max 200`. |
| Network cache seems stale | Bump `--ttl` down, or let it expire. The cache lives at `~/.opencli/cache/browser-network/`. |

---

## Data Extraction Patterns

Decision tree when scraping structured data from SPA:

0. **classify parent components first** — `browser state` to identify every major container on the page (Swipers, card grids, hero sections, nav bars). Each container is its own extraction unit with its own output directory. Skip this step and assets from different sections WILL get mixed together — a Swiper's images ending up in another component's folder is the #1 cause of "货不对板" bugs.
1. sniff: browser network --all -> found JSON/API? -> curl (best)
2. fallback: download JS bundle -> regex + brace-counter parse (JS exports like `worldImgs` / `cardList` / `heroBg` tell you which component owns which assets)
3. fallback: el.__vue_app__ / fiber walk component tree
4. last resort: DOM click + extract, atomic units, <10s each

CDN anti-leech image download:

- curl returns 301/404/HTML. Fix: load img into browser cache -> fetch(url) -> Blob -> download
- Verify: file img.webp reports "PNG/WebP image data", not "HTML document"
- Extension detection: read real ext from DOM src attribute, don't trust URL

JS bundle extraction:

```bash
grep -c "name\|title\|desc\|intro" bundle.js

node -e "
  const fs=require('fs'), content=fs.readFileSync('bundle.js','utf-8');
  const re=/{name:\"([^\"]+)\"/g; let m, res={};
  while((m=re.exec(content))!==null){
    let d=0, end=m.index;
    for(let i=m.index;i<content.length;i++){
      if(content[i]==='{')d++; else if(content[i]==='}'&&--d===0){end=i+1;break}
    }
    const e=content.slice(m.index,end);
    const cv=e.match(/cvname:\"([^\"]*)\"/); if(!cv||!cv[1])continue;
    res[m[1]]={en:(e.match(/enname:\"([^\"]+)\"/)||[])[1]||'',line:(e.match(/line:\"([^\"]*)\"/)||[])[1]||'',cv:cv[1]};
  }
  console.log(Object.keys(res).length+' entries'); fs.writeFileSync('out.json',JSON.stringify(res,null,2));
"
```

Common pitfalls:

- curl returns HTML/8KB: browser cache -> fetch + Blob URL
- .webp is actually .png: read real ext from DOM src
- minified JS has V()/q.xx, JSON.parse fails: regex + brace-counter
- eval loop "operation aborted": split into atomic units, one click per call
- dot notation keys (dengdeng vs 灯灯): locate by cvname field, not key value

---

## Design Replication Trigger

**WHEN the user expresses intent to replicate a page's visual design with high fidelity**, the agent MUST follow the mandatory four-phase Full Replication Pipeline (see below): Download → Visual Analysis → Relationship Inference → Handoff Document. Never skip phases. This trigger fires on phrases that signal pixel-perfect replication demand.

### Trigger phrases

Chinese: 一模一样, 完全一样, 尽量一模一样, 复刻, 1:1复刻, 像素级, 原样, 照搬, 克隆, 高保真, 百分之百还原, 100%还原

English: exactly like, identical, pixel-perfect, 1:1 copy, replicate exactly, clone the design, match it perfectly, look exactly the same, 100% match, indistinguishable from the original

### When it fires

The trigger activates when BOTH conditions are true:

1. Agent is in a page-scraping/inspection workflow (has run `browser open`, `browser state`, `browser screenshot`, or `browser eval` against a target site)
2. User says the current or upcoming implementation should look "exactly like" the referenced page

### How it fires

When trigger activates, use `AskUserQuestion` with `multiSelect: true`. Header: "复刻范围". Options:

| Label | Description |
|-------|-------------|
| 全量复刻 (推荐) | 四阶段流水线: 下载所有资源 → 视觉截图分析 → 推断组件关系 → 交付文档。覆盖视频/图片/CSS/JS/字体/HTML结构 |
| 仅背景+视觉 | 下载背景图片/视频 + 截图视觉分析。不下载 CSS/JS/HTML 结构 |
| 仅截图参考 | 只截图 + 视觉分析，不下新资源。用已有文件复刻 |

Pre-select "全量复刻 (推荐)" for 一模一样/复刻/pixel-perfect triggers.

When "全量复刻" is selected, proceed directly to the Full Replication Pipeline below without further AskUserQuestion calls — the pipeline is fully automatic.

### Full Replication Pipeline (四阶段流水线)

When user triggers full 1:1 replication (一模一样/复刻/pixel-perfect), follow this **mandatory four-phase pipeline**. Never skip phases or reorder them — download before vision, vision before inference, inference before handoff.

**Phase 1: Crawl & Download (先下载)**

Download everything before any analysis. You cannot analyze what you don't have.

0. **Classify parent components first:** `browser state` to identify every major container on the page (Swipers, card grids, hero sections, nav bars, route anchors). Each container = own extraction unit + own output directory. Also extract all route/hash/section identifiers found — these drive Phase 2 per-section analysis.
1. **Capture network cache:** `browser network --all` to get all resource URLs
2. **Video/Audio:** Filter for `video/mp4`, `video/webm` — `browser eval` to find `<video>` src. curl to `<project>/public/assets/video/`
3. **Images (per-component, from step 0):** Do NOT dump all images into one folder. For each parent component identified in step 0, collect its images separately — record `{ parentSelector, dataKey, src }` triples — then download into component-specific directories:
   ```
   <project>/public/assets/<component-a>/  ← images owned by component A
   <project>/public/assets/<component-b>/  ← images owned by component B
   ```
   Collect via `browser eval`: walk `document.images` + `getComputedStyle` `background-image`, but always annotate each URL with its closest identifiable parent container (`id`, `data-*`, or distinctive class). Filter out data: URIs. If the JS bundle (step 2) exports image-map objects, cross-reference them to confirm which component each batch belongs to.
4. **CSS bundles:** Filter network entries for `ct: "text/css"`. curl each to `<project>/scraped/css/`
5. **JS bundles:** Filter network entries for `ct: "application/javascript"` or `ct: "text/javascript"`. curl to `<project>/scraped/js/`
6. **Fonts:** From CSS `@font-face` rules, extract `url()`. curl to `<project>/scraped/fonts/`

**Asset verification after each download:** Verify file is not HTML/404:
- Images: first 4 bytes — PNG=`\x89PNG`, WebP=`RIFF`, JPEG=`\xFF\xD8\xFF`, MP4=`ftyp`
- CSS: first line contains `@charset` or CSS rule, not `<html`
- JS: first line is valid JS, not `<html`
- If verification fails: re-download via browser cache (`fetch()` from the live page)

**Phase 2: Visual Analysis (再视觉)**

Bridge DOM structure to visual semantics via annotated screenshots + vision model. Vision model reads `[N]` labels from screenshot and describes *what* each element is; you cross-reference against DOM for exact positions, sizes, class names. Never ask vision model for pixel coordinates.

1. **Discover sections:** From Phase 1 `browser state` + `network` results, extract all route/hash/section identifiers found on the page. Navigate to each for subsequent analysis.
2. **Extract DOM structure first:** `browser get html --as json --depth 6 --children-max 30` for the section. Note which `[N]` ref ranges belong to which container (sidebar, card grid, hero, etc.)
3. **Annotated screenshot:** `browser screenshot --annotate <project>/screenshots/<page>.png` — overlays `[N]` labels on visible elements. This is the bridge: vision model reads `[N]`, you map them to DOM refs.
4. **Vision analyze each annotated screenshot:**
   ```
   node vision.js "<screenshot>" "这张截图标注了 [N] 编号。请按以下结构输出清单，不要描述性段落。只描述你能在截图中看到的元素，不确定的标注'不确定'，不要编造不在截图中的组件。

   1. 背景层：哪些元素是背景（视频/图片/渐变）？在哪个 [N] 或 [N] 背后？
   2. 遮罩/叠加层：有没有半透明覆盖、渐变条、光效？在哪些 [N] 上方或之间？
   3. 组件识别：每个有 [N] 标签的元素是什么——标题/按钮/卡片/图标/导航项？
   4. 视觉层级：哪些在前景哪些在后景？同一区块内部怎么排列（横排/竖排/网格）？
   5. 颜色氛围：主色调、强调色、亮暗对比、渐变方向。
   6. 动效线索：哪些区域看起来有动画（轮播/淡入/视差/粒子/数字跳动）？"
   ```
5. **Extract CSS theme:** `browser eval` to get `getComputedStyle` key colors, gradients, spacing, font stacks on body and major containers.
6. **Cross-reference + filter:** For each item vision model reports, verify against DOM — DOM is ground truth.
   - `[N]` matches DOM element → record tag/class/dimensions/computed style → trusted
   - `[N]` in screenshot but NOT in DOM → vision model may be wrong → mark "uncertain"
   - vision says "has a button" but no `[N]` ref → hallucination → discard

**Phase 3: Relationship Inference (再推断)**

From vision output + downloaded assets + DOM structure, infer the architecture.

1. **Map asset → section:** Which background image/video belongs to which page section? Match by class name + visual context
2. **Map component → data:** What data drives each component? Check `__vue_app__` / React fiber or JS bundle grep
3. **Build component tree:** For each page section, draw the nesting: wrapper → background layer → content layer → individual components
4. **Identify shared vs unique layers:** Global video background (shared) vs per-section static bg crossfade (unique) vs decorative overlays
5. **Write intermediate output:** Save raw inference results to `<project>/docs/inference-raw.md` — asset-to-section map, component-to-data map, per-section component trees, shared/unique layer classification. This file is consumed by Phase 4 and deleted after final document is assembled.

**Phase 4: Handoff Document (交付文档)**

Write a structured AI-readable document at `<project>/docs/replication-map.md`. This document is consumed by the implementation agent (grill-super Phase 4). Optimize for agent readability — machine-parseable structure, no decorative prose, no ambiguous descriptions.

Each section is tagged: `[必写]` = always required, `[有则写]` = write only if the source page has it.

---

**[必写] 1. File Inventory**

Every downloaded asset with absolute path, what it is, and which component/section owns it.

```
public/assets/<dir>/<file>  →  <description>  —  <owner section/component>
```

- Image, video, font, CSS, JS — one entry per file
- Description: what it looks like (not just "image"), e.g. "dark nebula background, 1920x1080" not "bg.png"
- Owner: which section or component it belongs to (matches component tree section 2)

---

**[必写] 2. Component Tree — Per Section**

For each page section (route / hash / anchor), the exact DOM nesting with CSS class names and purpose. One tree per section.

```
#<route>:
  .<wrapper-class>
    .<bg-layer-class>          → <purpose, z-position, behavior>
    .<content-container>
      .<component-a>           → <purpose, child-of-what>
        .<child>               → <purpose>
      .<component-b>           → <purpose>
```

- Class names from actual DOM, not invented
- Each node annotated with its role (background / nav / card grid / hero / footer / overlay)
- Indentation = nesting depth

---

**[必写] 3. Layer Stack — Per Section**

Visual z-order per section, back-to-front.

```
#<route> layer stack:
  z-0: .<bg-layer>         — <opacity, blend-mode, filter, fixed/absolute>
  z-1: .<content-area>     — <positioning>
  z-2: .<overlay>          — <opacity, hover/persistent, transition>
  ...
```

- z-order relative to each other (not raw z-index numbers unless extracted from DOM)
- Opacity, blend mode, blur/filter, position (fixed/absolute/relative)
- Mark shared layers: "[shared — all sections]" vs "[unique to this section]"

---

**[必写] 4. Color Tokens**

Exact values from `getComputedStyle` or CSS variables. Group by role, not by element.

```
Backgrounds:
  page-bg:       <hex/rgba>
  card-bg:       <hex/rgba>
  overlay-bg:    <hex/rgba>

Text:
  text-primary:   <hex/rgba>
  text-secondary: <hex/rgba>
  text-muted:     <hex/rgba>

Accents:
  accent-primary: <hex/rgba>
  accent-hover:   <hex/rgba>
  divider:        <gradient or hex/rgba>

Borders / Shadows:
  card-shadow:    <box-shadow value>
  border-color:   <hex/rgba>
```

- Group semantically (backgrounds / text / accents / borders)
- Gradients written as full CSS value, not prose description
- If source uses CSS custom properties, capture the variable name too

---

**[必写] 5. Typography Tokens**

Font stacks, sizes, weights, line-heights from computed styles.

```
Font families:
  display:   "<font-name>", <fallback>
  body:      "<font-name>", <fallback>

Scale (per role):
  hero-title:    <size>px, weight <N>, line-height <N>
  section-title: <size>px, weight <N>, line-height <N>
  body:          <size>px, weight <N>, line-height <N>
  caption:       <size>px, weight <N>, line-height <N>
```

- Capture actual computed `font-family`, not what CSS says
- Only list roles that exist on the page — don't invent
- Note any `letter-spacing`, `text-transform`, `font-style` that deviates from default

---

**[必写] 6. Spacing Tokens**

Recurring gap/padding/margin patterns from computed styles.

```
Layout gaps:
  section-gap:     <N>px
  card-gap:        <N>px
  grid-column-gap: <N>px
  grid-row-gap:    <N>px

Padding:
  section-padding: <N>px
  card-padding:    <N>px
  button-padding:  <N>px vertical, <N>px horizontal
```

- Only values that repeat across multiple elements (not one-off)
- If no clear pattern, note range: "card padding varies 16-24px"

---

**[有则写] 7. Responsive Breakpoints**

If the source page has different layouts at different widths. Screenshot at 1920px, 1280px, 768px, 480px if responsive behavior observed.

```
Breakpoints:
  >= 1280px:  <layout description, column count>
  768-1279px: <layout changes>
  < 768px:    <layout changes>
```

- Only if the page actually changes layout — skip for fixed-width pages
- Note: column count changes, nav collapse, font size shifts

---

**[有则写] 8. Animation Map**

Every motion behavior observed, with timing and trigger.

```
<section/component>: <what animates>
  trigger:  <page load / scroll / hover / click / hash change>
  from:     <opacity/transform start state>
  to:       <opacity/transform end state>
  duration: <estimated seconds, or "unknown — approx Ns">
  ease:     <observed or guessed from visual>
  stagger:  <if items animate sequentially, interval>
```

- Only observed animations — don't invent
- If timing is unclear, mark as estimate
- Note tech if identifiable: "CSS transition", "GSAP tween", "canvas"

---

**[有则写] 9. Data Flow**

Which data source drives which component. From JS bundle grep, __vue_app__ walk, or network API capture.

```
<data source>  →  <component/section>
  Example: lore.json factions[] → sidebar.render() + grid.render()
```

- If from API, include endpoint URL and response shape summary
- If from JS bundle object, include variable name
- Mark "unknown" if Phase 3 couldn't determine — implementation agent knows to search

---

**[有则写] 10. Uncertain Items**

Everything marked "uncertain" from Phase 2 cross-reference, plus any gaps noticed during Phase 3.

```
- [N]=<ref>: vision says "<claim>", DOM: <reality> → <resolution suggestion>
- <section>: <missing info> → <what to check or default to>
```

- One item per line, actionable resolution
- If no uncertain items, write: "None — all items verified against DOM."

**How to write this document:** Read `<project>/docs/inference-raw.md` (Phase 3 output). Assemble each of the 10 sections below by extracting relevant data from that file + Phase 2 cross-reference results. Do not invent or guess — every value must trace back to Phase 2/3 evidence.

**After writing the final document:** Verify all 10 sections are complete. Then delete the intermediate file:
```
rm <project>/docs/inference-raw.md
```
The intermediate file served its purpose — Phase 4 assembled from it; now it would only go stale.

**Phase ordering is strict.** You cannot infer relationships (Phase 3) without first seeing the pages (Phase 2). You cannot analyze visuals (Phase 2) without first downloading assets (Phase 1). Violating this order wastes round-trips and produces incomplete replication.

### Non-trigger examples

These do NOT fire the trigger (no AskUserQuestion needed):
- "爬取一下这个页面的结构" (fact-finding, no replication intent)
- "看看这个页面用了什么颜色" (specific question, not replication)
- "分析一下这个导航栏" (component analysis, not full replication)
- "参考这个页面的布局" (reference/inspiration, not 1:1 copy)

---

## See also

- `opencli-adapter-author` — turning what you just figured out into a reusable `~/.opencli/clis/<site>/<command>.js`.
- `opencli-browser-sitemap` — consuming site sitemap context while driving a browser task.
- `opencli-sitemap-author` — creating or updating sitemap knowledge when you discover a durable path or stale entry.
- `opencli-autofix` — when an existing adapter breaks, this skill walks you through `--trace retain-on-failure` evidence and filing a fix.
