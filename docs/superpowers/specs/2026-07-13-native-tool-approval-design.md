# Native Tool Approval Design

## Goal

Restore Accept and Reject as a generic permission boundary around real tool side effects without restoring the removed decision JSON or fixed plan executor.

## Behavior

- The model remains responsible for understanding the user and requesting tools.
- A tool-owned permission policy decides whether the exact requested operation needs approval.
- Before a protected tool runs, the runtime saves the native assistant tool-call message, exact arguments, remaining calls, and conversation checkpoint in the session.
- No protected side effect occurs before approval.
- Accept executes the saved call once and resumes the native model/tool conversation.
- Reject adds a truthful tool result saying the user rejected that call, then lets the model answer or choose another approach.
- Read-only operations do not request approval merely because their tool also supports writes.
- Terminal commands and browser buttons use the same resume method.

## Non-goals

- No keyword intent detection.
- No custom model decision JSON.
- No fixed research plan or fixed tool sequence.
- No evaluator or acceptance report may approve actions automatically.

## Verification

- A protected write pauses before executor invocation.
- Accept executes the exact saved request and resumes the model.
- Reject never invokes the executor and reaches the model as a tool observation.
- Workspace list/read/search remain immediate.
- Browser buttons and API endpoints build and respond normally.
