# Context Budget Hardening

## Outcome

Prevent large tool payloads from entering the model conversation while preserving complete results as local artifacts. Keep task selection and research reasoning model-led.

## Non-goals

- No workbench UI changes.
- No provider or model migration.
- No broad rewrite of the capability/plugin system.
- No domain-specific routing for EEG, MDD, CNN, Transformer, or similar terms.

## Acceptance criteria

1. Every successful tool result is persisted in full outside model messages.
2. A single tool observation has its own configurable budget and cannot consume the whole conversation budget.
3. Request fitting includes system instructions, tool schemas, conversation messages, and an output reserve.
4. Persisted model messages do not contain raw tool data, while artifact references remain usable.
5. A regression test with a literature-shaped payload proves the next model call stays compact.
6. Existing core tests pass; environment-dependent tests are reported rather than masked.
7. A final audit reports semantic hardcoding that could restrict model decisions; deterministic safety, schemas, and resource limits are not treated as semantic routing.

## Design

`ContextManager` owns a generic observation envelope. It writes the complete observation to `tool_observations/`, then returns only the amount of data allowed by the smaller of the remaining request room and the configured observation budget. Oversized messages are replaced with a short completion summary and `data_ref`; raw `data` never crosses the observation cap.

Before every model request, `AgentLoop` builds the stable system and tool catalog, then asks `ContextManager` to fit conversation messages around that fixed cost and an output reserve. Token measurement remains provider-neutral: exact provider usage is recorded for monitoring, while preflight uses a conservative structural estimate.

Full observations remain available on disk and through artifacts. Session state stores compact observation metadata instead of duplicating complete paper arrays in `session.json`.

## Verification

- Unit test the observation envelope with a payload below the total context budget but above the per-observation budget.
- Agent-loop regression test confirms a large literature result does not appear in the following model request.
- Run focused context/agent tests, then the full suite.
- Scan the active runtime for keyword routing, domain aliases, canned workflow selection, and duplicated capability decisions.

## Verification results

- Historical replay of the two oversized literature observations reduced the model-visible estimates from 415,984 and 123,256 tokens to 838 and 822 tokens. The combined next request, including the stable system prompt and tool catalog, estimated 6,485 tokens plus an 8,000-token output reserve under the 32,000-token ceiling.
- After the user installed the local dependencies, the complete suite passes: 114 tests. The remaining streaming failure exposed a real adapter mismatch: requests marked `stream=true` were still buffered with `response.read()`. The compatible provider now iterates SSE lines as they arrive while preserving the non-streaming JSON path.
- The active chat path uses the native model/tool loop and does not import the legacy rule planner, intent parser, or workflow engine.
- Planning safety now reads `write_access` from capability metadata instead of comparing handler names.
- Literature relevance scores now rank results only. They cannot veto a paper that satisfies explicit constraints, and exploratory searches do not hard-exclude low-score candidates.

## Remaining hardcoding audit

- `STOPWORDS`, `ALIASES`, query expansion counts, source request caps, and polite delays in the literature capability remain deterministic retrieval heuristics. They can affect ordering and request volume, but they do not choose the user's task or discard exploratory evidence; the complete raw pool remains persisted.
- Slash commands, approval gates, duplicate-call guards, schemas, and context budgets remain deterministic by design. They are protocol, safety, or resource boundaries rather than semantic task routing.
- Legacy planner/workflow modules remain in the repository for compatibility tests, but the active runtime does not call them. They were not deleted because this change is not a cleanup rewrite.
