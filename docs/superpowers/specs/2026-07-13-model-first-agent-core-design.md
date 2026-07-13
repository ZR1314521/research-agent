# Model-first research agent core

## Product boundary

DeepSeek owns language understanding, task decomposition, tool choice, continuation, and the final answer. Runtime code owns only model transport, real tool execution, permission enforcement, persistence, cancellation, and truthful error handling.

The interactive path must not route requests through keyword intent rules, fixed research workflows, or a custom decision JSON protocol. JSON remains an internal API/tool representation only.

## Runtime

The runtime keeps an ordered native conversation containing user, assistant, tool-call, and tool-result messages. The model may answer directly or call any registered capability. Tool results are returned to the same conversation so the model can decide what to do next. Existing scientific capability implementations remain reusable and independently callable.

Safety checks may reject an unauthorized path, destructive action, invalid argument, or repeated no-progress call. They may not infer the user's research intent or select a workflow.

## User-outcome observation

Acceptance is a passive observer. For every turn it records the request, final answer, tool calls, errors, repeated calls, mutations, and verified artifacts, then emits a readable Markdown report. It never changes prompts, tool availability, routing, or execution.

## Compatibility

The browser and terminal entry points keep their existing public API shape. Legacy planner, intent, node, and workflow modules may remain for offline compatibility, but a configured model never enters them.

## Acceptance

- Natural conversation can finish without a tool.
- Native tool calls preserve assistant and tool messages across model requests.
- A completed tool result is still delivered if a later model request fails.
- File inspection supports locating relevant content instead of returning only a fixed prefix.
- Unauthorized filesystem writes are rejected at the tool boundary.
- Acceptance reports describe outcomes without influencing them.
