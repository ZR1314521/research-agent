# Research Agent Workbench -- 系统架构文档

## 1. 整体拓扑

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           浏览器 (localhost:3000)                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  HomePage │  │ WorkspacePage│  │TaskCenterPage│  │  SettingsPage  │  │
│  │  (纯展示)  │  │  (科研工作台) │  │  (任务中心)   │  │   (设置)       │  │
│  └──────────┘  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │
│                       │                 │                   │           │
│  ┌────────────────────┴─────────────────┴───────────────────┴────────┐  │
│  │                    App.js (SPA Router, hash-based)                 │  │
│  │           fetch / SSE / NDJSON stream → http://127.0.0.1:8877     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                         HTTP (loopback only)
                                    │
┌───────────────────────────────────┴──────────────────────────────────────┐
│                        FastAPI Server (127.0.0.1:8877)                    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                         app.py (create_app)                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │  │
│  │  │ /health       │  │ /setup/*     │  │ /runs/{id}/turns/stream  │ │  │
│  │  │ /sessions     │  │ /data-sources│  │ /runs/{id}/pause/resume  │ │  │
│  │  │ /chat         │  │ /styles      │  │ /runs/{id}/approve/reject│ │  │
│  │  │ /usage        │  │ /settings/*  │  │ /runs/{id}/files (upload)│ │  │
│  │  │ /schedules    │  │              │  │ /runs/{id}/events (SSE)  │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘ │  │
│  └───────────────────────────┬────────────────────────────────────────┘  │
│                              │                                           │
│  ┌───────────────────────────┼────────────────────────────────────────┐  │
│  │                   核心调度层                                        │  │
│  │                                                                     │  │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌────────────────┐  │  │
│  │  │  TurnCoordinator │   │  ScheduleService │   │  PlatformStore │  │  │
│  │  │  (一 Run 一 Turn)│   │  (定时任务调度)   │   │  (数据源/偏好) │  │  │
│  │  └────────┬─────────┘   └──────────────────┘   └────────────────┘  │  │
│  │           │                                                        │  │
│  └───────────┼────────────────────────────────────────────────────────┘  │
│              │                                                           │
└──────────────┼───────────────────────────────────────────────────────────┘
               │
┌──────────────┼───────────────────────────────────────────────────────────┐
│              ▼              ResearchChatAgent (chat.py)                   │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    AgentLoop (core/agent.py)                      │    │
│  │                                                                   │    │
│  │   ┌─────────┐    ┌──────────┐    ┌───────────┐    ┌───────────┐  │    │
│  │   │ Model   │───▶│  Tool    │───▶│  Execute  │───▶│  Observe  │  │    │
│  │   │  Call   │    │  Calls   │    │  Tools    │    │  & Loop   │  │    │
│  │   │  (LLM)  │◀───│ (Native) │◀───│ (Local)   │◀───│ (Repeat)  │  │    │
│  │   └─────────┘    └──────────┘    └───────────┘    └───────────┘  │    │
│  │        │              │               │               │          │    │
│  │   ┌────┴────┐   ┌─────┴──────┐  ┌────┴──────┐   ┌────┴─────┐    │    │
│  │   │LLMClient│   │SkillRegistry│  │ToolExecutor│  │ Session  │    │    │
│  │   │(OpenAI  │   │(contracts)  │  │(capability │  │ Store    │    │    │
│  │   │compat)  │   │             │  │ handlers)  │  │ (JSON)   │    │    │
│  │   └─────────┘   └─────────────┘  └────────────┘  └──────────┘    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 请求生命周期 (一条用户消息的完整路径)

```
用户输入 "找近3年CNN BCI EEG论文"
  │
  ▼
┌─ App.js ─────────────────────────────────────────────────────────────┐
│  startTurn(text)                                                     │
│    POST /runs/{run_id}/turns/stream  {message: text}                 │
└──────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ app.py ─────────────────────────────────────────────────────────────┐
│  stream_turn(run_id, request)                                        │
│    ├─ load_run(run_id)          → ChatSession                        │
│    └─ coordinator.start(run_id, message)                             │
│         └─ TurnCoordinator._run(control, message)  [daemon thread]   │
│              │                                                       │
│              ▼                                                       │
│         ResearchChatAgent.handle(session, message, ...)              │
│              │                                                       │
│              ▼                                                       │
│         AgentLoop.run(session, user_message)                         │
│              │                                                       │
│              ▼                                                       │
│         AgentLoop._drive(session, messages, user_message, state)     │
└──────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ AgentLoop._drive ── (ReAct loop, max N turns) ─────────────────────┐
│                                                                      │
│   while True:                                                        │
│     │                                                                │
│     ├─ 1. LLMClient.chat(messages, system, tools)                    │
│     │      └─ POST {llm_base_url}/chat/completions                   │
│     │      └─ 返回: text + tool_calls (OpenAI-compatible)            │
│     │                                                                │
│     ├─ 2. 无 tool_calls?                                             │
│     │      ├─ planning mode → pause_for_plan_approval()              │
│     │      └─ active mode    → finish(session, message, ...)         │
│     │                                                                │
│     ├─ 3. 有 tool_calls?                                             │
│     │      ├─ 检查是否需要用户确认 (batch_requires_confirmation)      │
│     │      │    └─ 需要 → pause_for_tool_approval()                  │
│     │      │                                                        │
│     │      └─ 不需要 → _execute_calls(session, raw_calls, ...)       │
│     │           │                                                   │
│     │           ├─ for each tool_call:                               │
│     │           │    ├─ SkillRegistry.resolve(name) → SkillSpec      │
│     │           │    ├─ 去重检查 (seen_calls)                        │
│     │           │    ├─ 网络/写权限检查                               │
│     │           │    └─ ToolExecutor.execute(name, args, session)    │
│     │           │         ├─ validate_arguments(schema, args)        │
│     │           │         ├─ 检查 artifact 依赖 (consumes)           │
│     │           │         ├─ handler(args, session) → result         │
│     │           │         └─ validate_result_quality(result)         │
│     │           │                                                   │
│     │           └─ 所有 direct_delivery → 直接返回给用户             │
│     │                                                                │
│     └─ 4. goto 1 (tool results 作为 observation 注入 messages)       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─ 返回 & 流式推送 ─────────────────────────────────────────────────────┐
│   AgentLoop 返回 AgentResult(message, skill)                          │
│     → TurnCoordinator 通过 control.emit() 推送 NDJSON 事件            │
│     → 前端 consume(response, generation) 逐条消费                     │
│     → 最终 emit("turn_finished", {assistant_message, artifacts, ...}) │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 模块层次结构

```
research_agent/
│
├── 入口层
│   ├── cli.py            # 终端入口 (python -m research_agent)
│   ├── app.py            # FastAPI 应用工厂 (create_app)
│   └── chat.py           # ResearchChatAgent 顶层门面
│
├── 核心引擎 (core/)
│   ├── agent.py          # AgentLoop: 模型-工具 ReAct 循环
│   ├── contracts.py      # 工具契约校验 (参数/产物/质量)
│   ├── decision.py       # 审批策略
│   └── prompt_runtime.py # 系统提示词组装
│
├── 调度与协调
│   ├── turns.py          # TurnCoordinator + TurnControl (NDJSON 流)
│   ├── scheduler.py      # ScheduleService (定时任务)
│   └── workflow.py       # 工作流编排
│
├── 能力层 (capabilities/)
│   ├── literature.py     # 文献检索 (OpenAlex/PubMed/SemanticScholar)
│   ├── writing.py        # 写作 (综述/章节/润色/可视化)
│   ├── documents.py      # 文档转换 (DOCX/Markdown)
│   ├── references.py     # 参考文献格式化 (GB/T 7714, IEEE, Nature…)
│   ├── rag.py            # 本地 RAG (向量检索)
│   ├── data_analysis.py  # 实验数据分析 (统计/异常/图表)
│   ├── data_transform.py # 数据转换
│   ├── arxiv_reader.py   # arXiv 论文读取
│   ├── papers.py         # 开放获取论文下载
│   ├── web_search.py     # Web 搜索
│   ├── web_fetch.py      # Web 抓取
│   ├── code_runner.py    # 代码执行沙箱
│   ├── files.py          # 文件注册/上传
│   ├── workspace.py      # 工作区文件操作
│   ├── git_ops.py        # Git 操作
│   ├── shell.py          # Shell 执行
│   └── quality.py        # 质量审计
│
├── 工具注册与执行
│   ├── skill_registry.py # SkillSpec + SkillRegistry (声明式契约)
│   ├── executor.py       # ToolExecutor (路由 → 校验 → 执行)
│   └── tools/            # 外部工具客户端
│       ├── llm_client.py     # LLMClient + ModelGateway
│       ├── openalex.py       # OpenAlex API
│       ├── pubmed.py         # PubMed API
│       ├── semantic_scholar.py # Semantic Scholar API
│       └── arxiv.py          # arXiv API
│
├── 状态与持久化
│   ├── session.py        # ChatSession + SessionStore (JSON 文件)
│   ├── state.py          # 工作流状态机
│   ├── run_store.py      # RunStore (SQLite 镜像)
│   ├── platform_store.py # PlatformStore (设置/数据源/隐私)
│   └── context.py        # ContextManager (token 预算/截断)
│
├── 横切
│   ├── config.py         # AgentConfig (.env 加载)
│   ├── logging.py        # ModelCallLogger
│   ├── provider_runtime.py # ProviderEvent, CallLedger, call_context
│   ├── usage.py          # UsageService (用量统计)
│   ├── acceptance.py     # UserOutcomeObserver (质量追踪)
│   ├── intent.py         # 意图识别
│   ├── planner.py        # 任务规划
│   ├── prompts/          # 系统提示词模板
│   │   └── agent_system.md
│   └── version.py        # RUNTIME_VERSION
│
└── nodes/ (LangGraph 风格节点)
    ├── base.py           # 节点基类
    ├── checkpoint.py     # 检查点
    ├── literature_search.py
    ├── recursive_screen.py
    ├── matrix_extract.py
    ├── experiment_analysis.py
    ├── review_draft.py
    ├── reference_format.py
    ├── rag.py
    └── upload.py
```

---

## 4. 前端架构 (workbench/)

```
workbench/
├── public/index.html
├── build/                          # React build 产物
│   ├── index.html                  # SPA 入口 (Research Agent Workbench)
│   └── static/js/main.*.js
│
└── src/
    ├── index.js
    ├── App.js                      # 单文件 SPA 主体
    │   ├── 页面路由 (hash-based)
    │   │   ├── #/home       → HomePage
    │   │   ├── #/workspace  → WorkspacePage (内联)
    │   │   ├── #/tasks      → TaskCenterPage
    │   │   └── #/settings   → SettingsPage
    │   │
    │   ├── 核心状态
    │   │   ├── runId, messages, sessions
    │   │   ├── turnState, activeTurnId
    │   │   ├── pendingApproval, planActive
    │   │   └── tokenUsage, modelName
    │   │
    │   ├── 流式消费 (NDJSON via fetch + ReadableStream)
    │   │   └── consume() → handleEvent() 状态机
    │   │
    │   └── 操作
    │       ├── startTurn()    → POST /runs/{id}/turns/stream
    │       ├── control()      → POST /runs/{id}/{pause|resume|cancel}
    │       ├── resolveApproval() → POST /runs/{id}/{approve|reject}
    │       ├── upload()       → POST /runs/{id}/files (multipart)
    │       └── switchSession()/newRun()
    │
    ├── components/
    │   ├── TopNav.js              # 顶部导航栏 (Home/Workspace/Tasks/Settings)
    │   ├── AdaptiveLogo.js        # 自适应 Logo
    │   └── ApprovalDock.js        # 审批卡片 (Accept/Reject)
    │
    └── pages/
        ├── HomePage.js            # 首页 (Hero + 6 能力模块)
        ├── SettingsPage.js        # 设置 (快速配置/模型/数据源/隐私)
        └── TaskCenterPage.js      # 任务中心 (会话列表/状态筛选)

视觉系统: 奶油风 (暖象牙白 + 鼠尾草绿 + 低饱和辅色)
```

---

## 5. 数据流与持久化

```
runs/
├── platform.sqlite3            # PlatformStore (设置/数据源/定时任务)
└── sessions/
    └── {session_id}/
        ├── session.json        # ChatSession 完整快照
        ├── workflow_trace.json # 事件流副本
        ├── execution_log.jsonl # 事件日志 (追加)
        ├── provider_calls.jsonl# LLM 调用记录 (CallLedger)
        ├── model_call_log.jsonl# 详细模型调用日志
        ├── turn_{turn_id}.jsonl# 单 Turn NDJSON 事件流
        ├── tool_observations/  # 工具执行结果 (uuid.json)
        ├── context_sources/    # 截断上下文备份
        └── incoming_uploads/   # 上传文件
```

```
持久化双写策略:
  SessionStore.save(session)
    ├─ session.json          ← 主存储 (JSON 文件)
    └─ RunStore (SQLite)     ← 镜像 (replace_snapshot + append_event)
         └─ run_store.sqlite3
```

---

## 6. 工具契约系统

每个 Skill 在 `skills/registry.json` 中声明并在 `skill_registry.py` 的 `DECLARED_CONTRACTS` 中定义契约:

```
SkillSpec {
  name, kind, handler, description
  input_schema      ← JSON Schema (参数校验)
  output_schema     ← 输出结构校验
  consumes          ← 依赖的 Artifact 类型 (如 PaperPool)
  produces          ← 产出的 Artifact 类型 (如 ScreenedPaperPool)
  artifact_types    ← 产物文件扩展名映射
  network_access    ← 是否需要网络
  write_access      ← 是否写操作
  requires_confirmation ← 是否需要用户确认
  direct_delivery   ← 结果是否直接返回给用户
  planner_visible   ← 模型是否可调用
}
```

执行链路: `模型 tool_call → SkillRegistry.resolve() → ToolExecutor.execute() → validate_arguments() → has_required_artifacts() → handler() → validate_result_quality()`

---

## 7. TurnCoordinator 状态机

```
                    ┌─────────┐
        start() ──▶ │ running │
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌──────────┐ ┌────────┐ ┌──────────────┐
        │  paused  │ │cancelled│ │waiting_approval│
        └────┬─────┘ └────────┘ └───────┬──────┘
             │                          │
             │ resume()      approve()/reject()
             ▼                 ▼
        ┌─────────┐      ┌─────────┐
        │ running │      │ running │ (继续 AgentLoop)
        └─────────┘      └─────────┘

  终态: completed / failed / cancelled
```

每个 Turn 产生一个 NDJSON 事件流, 前端可以通过 turn_id + sequence 断线重连。

---

## 8. 关键技术决策

| 决策 | 说明 |
|------|------|
| **模型主导 (Model-led)** | 没有关键词路由器或隐藏的 planner/judge。模型通过 native tool calls 驱动所有操作 |
| **Provider-neutral** | LLMClient 使用 OpenAI-compatible 协议, 支持 DeepSeek/OpenAI/Qwen/Moonshot/Zhipu 等 |
| **Loopback-only** | API 和前端都在本地 (127.0.0.1), CORS 仅允许 localhost:3000 |
| **声明式契约** | 工具的参数/产物/权限全部在 `DECLARED_CONTRACTS` 和 `registry.json` 中声明, 不与执行代码耦合 |
| **双写持久化** | Session 主存为 JSON 文件, 同时镜像到 SQLite RunStore |
| **可恢复流** | 每个 Turn 持久化 NDJSON 事件流, 前端断线后可通过 `after_sequence` 重连 |
| **审批检查点** | 工具执行前可暂停等待用户 Accept/Reject, 状态持久化到 session.pending_action |
| **计划模式** | 只读规划模式 (/plan), 模型可搜索但不能写入; 发布后需用户审批才退出并执行 |
| **单文件 SPA** | React 18 单文件应用, hash 路由, 无额外 UI 框架依赖 |

---

## 9. 科研技能分类

```
文献检索
  ├── search_literature      (多源联合检索: OpenAlex/PubMed/SemanticScholar)
  ├── search_openalex        (OpenAlex 单独检索)
  ├── search_pubmed          (PubMed 单独检索)
  ├── search_semantic_scholar(Semantic Scholar 单独检索)
  ├── screen_papers          (论文筛选)
  ├── read_arxiv             (arXiv 论文读取)
  └── web_search             (通用 Web 搜索)

文献阅读与综述
  ├── summarize_papers       (论文摘要/矩阵提取)
  ├── write_review           (综述写作)
  ├── document_summary       (文档摘要)
  ├── rag_query              (本地 RAG 知识库查询)
  └── quality_audit          (质量审计)

实验数据分析
  ├── analyze_experiment     (实验数据分析与可视化)
  ├── transform_data         (数据转换)
  └── run_code               (代码执行)

参考文献管理
  ├── format_references      (格式化: GB/T 7714, IEEE, Nature, Science...)
  └── register_files         (文件注册/上传)

文档写作与编辑
  ├── write_paper_section    (论文章节写作)
  ├── revise_document        (文档修订)
  ├── humanize_text          (文本润色)
  ├── design_visual          (科研图表/可视化)
  ├── export_docx            (导出 DOCX)
  └── document_convert       (文档格式转换)

论文获取
  ├── acquire_open_access_papers (开放获取论文下载)
  └── create_reading_copy    (创建阅读副本 DOCX)

工作区操作
  ├── workspace_files        (文件 CRUD)
  ├── web_fetch              (网页抓取)
  ├── git                    (版本控制)
  └── shell                  (Shell 命令)
```

---

## 10. 部署与启动

```
start_workbench.ps1
  ├─ python -m uvicorn research_agent.app:app --host 127.0.0.1 --port 8877
  └─ npm start (workbench/) → React dev server :3000

start_agent.bat
  └─ python -m research_agent.cli   (终端模式)
```
