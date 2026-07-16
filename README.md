# AI Research Agent

Provider-neutral research agent with a browser workbench, CLI, and local skills.

The main runtime is model-led: the model responds or emits native tool calls,
tool results are appended to the same turn, and the model continues only when
another model round is necessary. There is no keyword router or hidden
planner/judge/wrap-up request in the main path.

This is not a fixed user-facing flow. Tools publish typed artifacts (for
example `WordDocument`, `PaperPool`, `EvidenceMatrix`, and `ReferenceList`),
and the model selects a compatible next operation. Invalid tool parameters are
rejected before execution and returned as an observable error for replanning.

## Start

```powershell
cd "C:\Users\Z18803231258\Documents\New project"
.\start_workbench.ps1
```

This starts the API at `127.0.0.1:8877` and the Web UI at `localhost:3000`.
Use `.\start_agent.bat` when you specifically want the CLI.

Then enter natural-language tasks:

```text
找近3年的CNN BCI EEG论文，只用OpenAlex，找5篇
这些论文都大概讲什么？
生成一份文献综述大纲
分析实验数据 "D:\data\experiment.xlsx" 的异常值和趋势
把这些参考文献转成GB/T 7714和IEEE格式
把综述导出成DOCX
```

While a step is running in the Windows terminal, press `Esc` to request
cancellation. Completed artifacts remain; the runtime will not start a later
ReAct step after the cancellation request.

Quote file paths containing spaces. Prefixing a path with `@` also works for
single-token paths.

## Commands

```text
/help /skills /status /pause /resume /new /model /model-test /exit
```

Sessions and outputs are stored under `runs/sessions/<session_id>/`. The next
startup resumes the latest session; use `/new` to start a clean one.

## Model

Configure the single project-root `.env` with an OpenAI-compatible endpoint.
Only the variables below are read for model selection; old provider aliases are ignored:

```env
RESEARCH_AGENT_LLM_PROVIDER=
RESEARCH_AGENT_LLM_BASE_URL=
RESEARCH_AGENT_LLM_MODEL=
RESEARCH_AGENT_LLM_API_KEY=
RESEARCH_AGENT_LLM_PROTOCOL=openai-compatible
RESEARCH_AGENT_LLM_TIMEOUT=120
RESEARCH_AGENT_LLM_RETRY=0
RESEARCH_AGENT_PROVIDER_MAX_CONCURRENCY=1
RESEARCH_AGENT_LLM_MAX_TOKENS=0
RESEARCH_AGENT_CONTEXT_WINDOW=0
```

`MAX_TOKENS=0` omits a fixed per-call output cap and `CONTEXT_WINDOW=0` avoids
guessing a provider window. The workbench does not expose synthetic call or
token quotas. Runtime efficiency comes from bounded context, merged tool
batches, and one screening pass per literature batch. Without a configured
model, the chat reports that clearly; it does not use keyword rules to pretend
it understood the request.

## HTTP chat endpoints

When FastAPI is installed, the same Agent Core is available through:

```text
POST /chat
POST /chat/stream
POST /runs
POST /runs/{run_id}/messages
POST /runs/{run_id}/turns/stream
GET  /runs/{run_id}/turns/{turn_id}/events?after_sequence=0
POST /runs/{run_id}/pause
POST /runs/{run_id}/resume
POST /runs/{run_id}/approve
POST /runs/{run_id}/reject
GET  /runs/{run_id}/provider-calls
```

## Local workbench

The browser workbench is intentionally loopback-only. Its one-command launcher
uses the installed Python runtime directly and does not change `PATH`:

```powershell
.\start_workbench.ps1
```

It starts `127.0.0.1:8877` and the React development server. Use
`./start_workbench.ps1 -DryRun` to inspect the two commands without launching
anything. The no-install bootstrap requires the already-provisioned local
artifact `workbench/node_modules/.bin/react-scripts.cmd`; if it is missing,
the launcher stops before starting either server and explains the requirement.

The workbench uses one NDJSON TurnStream per task. Reconnecting with a turn ID
and sequence only replays persisted local events; it does not call the model
again. The older message and SSE endpoints remain as compatibility adapters.
File uploads use standard `multipart/form-data`: submit one or more `files`
parts, each with its original filename and content. The local requirements
record the required `python-multipart` package. Successful uploads return the
current run's sequenced event and artifact snapshot.
