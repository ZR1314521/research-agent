import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import TopNav, { BrandMark } from "./components/TopNav";
import ApprovalDock from "./components/ApprovalDock";
import ArtifactList from "./components/ArtifactList";
import ContextMeter from "./components/ContextMeter";
import Icon from "./components/Icon";
import HomePage from "./pages/HomePage";
import SettingsPage from "./pages/SettingsPage";
import TaskCenterPage from "./pages/TaskCenterPage";
import { applyTheme, loadTheme } from "./theme";

const API_PORT = process.env.REACT_APP_API_PORT || "8878";
const API_HOST = process.env.REACT_APP_API_HOST || "127.0.0.1";
const API = String(process.env.REACT_APP_API_BASE || `http://${API_HOST}:${API_PORT}`).replace(/\/$/, "");
const BUSY = new Set(["running", "pause_requested", "paused", "waiting_approval", "rate_limited"]);

export function outcomeStepStatus(outcome, ok = true) {
  return ({
    success: "completed", partial: "partial", empty: "empty",
    rate_limited: "rate_limited", failed: "failed", cancelled: "cancelled",
  })[outcome] || (ok === false ? "failed" : "completed");
}

function stepStateLabel(status) {
  return ({
    completed: "已完成", partial: "部分完成", empty: "无结果", rate_limited: "来源限流",
    failed: "失败", cancelled: "已取消", running: "执行中", queued: "已排队",
  })[status] || "已完成";
}

function stepStateIcon(status) {
  return ({ running: "…", failed: "×", rate_limited: "!", partial: "!", empty: "○", cancelled: "–" })[status] || "✓";
}

function initialPage() {
  const value = window.location.hash.replace(/^#\/?/, "");
  return ["home", "workspace", "tasks", "settings"].includes(value) ? value : "home";
}

function statusLabel(value) {
  const labels = {
    idle: "就绪", active: "就绪", running: "运行中", pause_requested: "暂停中",
    paused: "已暂停", waiting_approval: "等待确认", rate_limited: "等待限流恢复",
    completed: "已完成", failed: "失败", cancelled: "已取消",
  };
  return labels[value] || value || "就绪";
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).pop() || path;
}

function WorkflowInspector({ runId, steps, artifacts, onClose }) {
  return (
    <aside className="run-inspector" aria-label="任务检查器">
      <header><button type="button" className="inspector-close" onClick={onClose} aria-label="关闭任务详情"><Icon name="x" size={18} /></button><span>Task details</span><h2>任务轨迹</h2><p>这里只展示可理解的步骤与成果，不展示内部日志和模型原始数据。</p></header>
      <section className="inspector-section">
        <div className="inspector-heading"><h3>执行步骤</h3><span>{steps.length}</span></div>
        <div className="inspector-steps">
          {steps.map(step => <article key={step.id || `${step.skill}-${step.started_at}`} className={`inspector-step ${step.status}`}><i /><div><strong>{step.status === "running" ? "正在处理" : step.summary || stepStateLabel(step.status)}</strong><span>{stepStateLabel(step.status)}</span></div></article>)}
          {!steps.length && <p className="inspector-empty">尚未执行工具。对话与一般问答不会伪造工作流步骤。</p>}
        </div>
      </section>
      <section className="inspector-section artifact-inspector">
        <div className="inspector-heading"><h3>任务产物</h3><span>{Object.keys(artifacts || {}).length}</span></div>
        <ArtifactList api={API} runId={runId} artifacts={artifacts} />
        {!Object.keys(artifacts || {}).length && <p className="inspector-empty">产物生成后会在这里显示预览或文件路径。</p>}
      </section>
    </aside>
  );
}

function CollapsibleReasoning({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="reasoning-block">
      <button type="button" className="reasoning-toggle" onClick={() => setOpen(v => !v)}>
        <Icon name={open ? "chevronDown" : "chevronRight"} size={14} />
        <span>{open ? "收起思考过程" : "查看思考过程"}</span>
      </button>
      {open && <div className="reasoning-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>}
    </div>
  );
}

function CollapsibleStep({ step }) {
  const summary = step.summary || stepStateLabel(step.status);
  const isLong = summary.length > 80;
  const [open, setOpen] = useState(false);
  return (
    <div className={`execution-step ${step.status}`}>
      <span>{stepStateIcon(step.status)}</span>
      <div className="execution-step-body">
        <div className="execution-step-head">
          <strong>{step.status === "running" ? "正在处理" : step.tool}</strong>
          {isLong && (
            <button type="button" className="step-toggle" onClick={() => setOpen(v => !v)}>
              {open ? "收起" : "查看详情"}
            </button>
          )}
        </div>
        {(!isLong || open) && <small>{summary}</small>}
      </div>
    </div>
  );
}

function CollapsibleCode({ language, children }) {
  const [open, setOpen] = useState(false);
  const label = language ? `技术输出（${language}）` : "技术输出";
  return (
    <span className="code-collapse-block">
      <button type="button" className="code-collapse-toggle" onClick={() => setOpen(v => !v)}>
        <Icon name={open ? "chevronDown" : "chevronRight"} size={14} />
        <span>{open ? "收起" : "查看"}{label}</span>
      </button>
      {open && <pre><code className={language ? `language-${language}` : ""}>{children}</code></pre>}
    </span>
  );
}

function WorkspacePage({
  runId, sessions, selectedSessions, setSelectedSessions, deleteMode, setDeleteMode,
  onDeleteSessions, onNewRun, onSwitchSession, turnState, modelName, contextSize, contextWindow,
  control, messages, msgDeleteMode, selectedMsgs, setSelectedMsgs, onDeleteMessages,
  pendingApproval, resolveApproval, error, files, setFiles, upload, styleGroups,
  convertFormat, planActive, startTurn, message, setMessage, busy, activeTurnId, bottomRef,
  artifacts, workflowSteps,
}) {
  const activeSession = sessions.find(session => session.run_id === runId);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailCount = workflowSteps.length + Object.keys(artifacts || {}).length;

  return (
    <main className="workspace-page page-frame">
      <aside className="conversation-sidebar">
        <button onClick={onNewRun} className="new-session-button"><Icon name="plus" className="btn-icon" />新建会话</button>
        <button className={`delete-session-button ${deleteMode ? "active" : ""}`} onClick={onDeleteSessions}>
          <Icon name="trash" className="btn-icon" />{deleteMode && selectedSessions.size ? `删除会话（${selectedSessions.size}）` : "删除会话"}
        </button>
        <div className="sidebar-section-title"><span>历史会话</span><small>{sessions.length}</small></div>
        <div className="session-list">
          {sessions.map(session => {
            const selected = selectedSessions.has(session.run_id);
            return (
              <button
                key={session.run_id}
                className={`session-item ${session.run_id === runId ? "active" : ""} ${selected ? "selected" : ""}`}
                onClick={() => {
                  if (deleteMode) {
                    const next = new Set(selectedSessions);
                    selected ? next.delete(session.run_id) : next.add(session.run_id);
                    setSelectedSessions(next);
                  } else onSwitchSession(session.run_id);
                }}
              >
                <span className="session-icon"><Icon name="document" size={16} /></span>
                <span className="session-body"><strong>{session.title || "新会话"}</strong><small>{String(session.updated_at || session.created_at || "").slice(0, 10)}</small></span>
                {deleteMode && <span className={`selection-dot ${selected ? "checked" : ""}`}>{selected ? "✓" : ""}</span>}
              </button>
            );
          })}
          {!sessions.length && <div className="sidebar-empty"><Icon name="activity" size={28} /><p>还没有历史会话</p></div>}
        </div>
        {deleteMode && <button className="cancel-selection" onClick={() => { setDeleteMode(false); setSelectedSessions(new Set()); }}>取消选择</button>}
      </aside>

      <section className="workspace-panel">
        <header className="workspace-header">
          <div className="workspace-heading">
            <h1>{activeSession?.title || "科研工作台"}</h1>
            <span className={`run-status status-${turnState}`}><i />{statusLabel(turnState)}</span>
          </div>
          <div className="workspace-header-actions">
            <button type="button" className="task-details-button" onClick={() => setDetailsOpen(true)}>任务详情{detailCount ? ` ${detailCount}` : ""}</button>
            <ContextMeter modelName={modelName} contextSize={contextSize} contextWindow={contextWindow} />
            <button type="button" onClick={() => control("pause")} disabled={turnState !== "running"}><Icon name="pause" className="btn-icon" />暂停</button>
            <button type="button" onClick={() => control("resume")} disabled={!(["paused", "pause_requested", "rate_limited"].includes(turnState))}><Icon name="play" className="btn-icon" />恢复</button>
            <button type="button" className="danger-soft" onClick={() => control("cancel")} disabled={!BUSY.has(turnState)}><Icon name="x" className="btn-icon" />取消</button>
          </div>
        </header>

        <section className="chat-timeline">
          {messages.length === 0 && (
            <div className="workspace-empty">
              <BrandMark />
              <h2>今天想完成什么科研工作？</h2>
              <p>直接描述目标，Agent 会按需要调用文献、数据、写作和文件工具。</p>
            </div>
          )}
          {messages.map((item, index) => {
            const selected = selectedMsgs.has(index);
            const isUser = item.role === "user";
            return (
              <div key={`${item.role}-${index}`} className={`message-row ${isUser ? "user-row" : "agent-row"}`}>
                {!isUser && <span className="message-avatar agent-avatar"><BrandMark /></span>}
                <article
                  className={`message-bubble ${item.role} ${selected ? "selected" : ""}`}
                  onClick={() => {
                    if (!msgDeleteMode) return;
                    const next = new Set(selectedMsgs);
                    selected ? next.delete(index) : next.add(index);
                    setSelectedMsgs(next);
                  }}
                >
                  <header><span>{isUser ? "你" : item.role === "system" ? "系统" : "Research Agent"}</span>{msgDeleteMode && <i>{selected ? "✓ 已选择" : "点击选择"}</i>}</header>
                  {(item.steps || []).length > 0 && <div className="execution-steps">
                    {(item.steps || []).map(step => <CollapsibleStep key={step.key} step={step} />)}
                  </div>}
                  {item.reasoning && <CollapsibleReasoning text={item.reasoning} />}
                  {item.content && (isUser || item.role === "system"
                    ? <div className="message-content plain-message">{item.content}</div>
                    : <ReactMarkdown
                        className="message-content markdown-message"
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: props => <a {...props} target="_blank" rel="noreferrer" />,
                          code: ({ inline, className, children }) => {
                            if (inline) return <code className={className}>{children}</code>;
                            const match = /language-(\w+)/.exec(className || "");
                            return <CollapsibleCode language={match ? match[1] : ""}>{String(children).replace(/\n$/, "")}</CollapsibleCode>;
                          },
                        }}
                      >{item.content}</ReactMarkdown>)}
                  {item.streaming && !item.content && !(item.steps || []).length && <div className="thinking-indicator"><i /><i /><i /><span>正在理解任务</span></div>}
                  <ArtifactList api={API} runId={runId} artifacts={item.artifacts} />
                </article>
                {isUser && <span className="message-avatar user-message-avatar"><i /></span>}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </section>

        <ApprovalDock pending={pendingApproval} onResolve={resolveApproval} />
        {error && <div className="workspace-error"><span>!</span>{error}</div>}

        <section className="composer-panel">
          <div className="composer-toolbar">
            <form onSubmit={upload} className="upload-form">
              <label htmlFor="workspace-files" className="tool-button"><Icon name="search" className="btn-icon" />上传文件</label>
              <input id="workspace-files" type="file" multiple onChange={event => setFiles(Array.from(event.target.files || []))} disabled={busy} />
              {files.length > 0 && <button className="upload-ready" disabled={!runId || busy}>上传（{files.length}）</button>}
            </form>
            <select className="format-select" onChange={convertFormat} disabled={!runId || busy} defaultValue="">
              <option value="" disabled>格式转换</option>
              {styleGroups.map(group => <optgroup key={group.group} label={group.group}>{group.items.map(style => <option key={style.key} value={style.key}>{style.name}</option>)}</optgroup>)}
            </select>
            <button className={`tool-button ${planActive ? "active" : ""}`} onClick={() => startTurn("/plan", false)} disabled={busy}>{planActive ? <><Icon name="check" className="btn-icon" />计划模式</> : <><Icon name="checkSquare" className="btn-icon" />计划模式</>}</button>
            <button className={`tool-button ${msgDeleteMode ? "active danger" : ""}`} onClick={onDeleteMessages}>{msgDeleteMode ? (selectedMsgs.size ? `确认删除（${selectedMsgs.size}）` : "选择消息") : <><Icon name="trash" className="btn-icon" />删除消息</>}</button>
          </div>
          <form onSubmit={event => { event.preventDefault(); startTurn(message, true); }} className="message-composer">
            <textarea
              value={message}
              onChange={event => setMessage(event.target.value)}
              onKeyDown={event => { if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); startTurn(message, true); } }}
              disabled={busy && turnState !== "paused"}
              placeholder={turnState === "paused" ? "输入调整要求，Agent 将在同一任务中继续…" : "描述你希望 Agent 完成的科研任务…"}
              rows={3}
            />
            <button disabled={!runId || !message.trim() || (busy && turnState !== "paused")} className="send-button"><span>{turnState === "paused" ? "调整并继续" : "发送"}</span><Icon name="send" size={16} /></button>
          </form>
          <div className={`composer-meta ${turnState === "paused" ? "intervention-meta" : ""}`}><span>{turnState === "paused" ? "当前任务已暂停；下一条消息会调整任务并继续" : "Ctrl + Enter 发送"}</span>{activeTurnId && <span>Turn {activeTurnId.slice(0, 8)}</span>}</div>
        </section>
      </section>
      {detailsOpen && <button type="button" className="inspector-backdrop" aria-label="关闭任务详情" onClick={() => setDetailsOpen(false)} />}
      {detailsOpen && <WorkflowInspector runId={runId} steps={workflowSteps} artifacts={artifacts} onClose={() => setDetailsOpen(false)} />}
    </main>
  );
}

export default function App() {
  const [page, setPage] = useState(initialPage);
  const [runId, setRunId] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedSessions, setSelectedSessions] = useState(new Set());
  const [deleteMode, setDeleteMode] = useState(false);
  const [msgDeleteMode, setMsgDeleteMode] = useState(false);
  const [selectedMsgs, setSelectedMsgs] = useState(new Set());
  const [artifacts, setArtifacts] = useState({});
  const [workflowSteps, setWorkflowSteps] = useState([]);
  const [error, setError] = useState("");
  const [files, setFiles] = useState([]);
  const [turnState, setTurnState] = useState("idle");
  const [activeTurnId, setActiveTurnId] = useState("");
  const [pendingApproval, setPendingApproval] = useState(null);
  const [planActive, setPlanActive] = useState(false);
  const [styleGroups, setStyleGroups] = useState([]);
  const [apiVersion, setApiVersion] = useState("");
  const [modelName, setModelName] = useState("");
  const [contextSize, setContextSize] = useState(0);
  const [contextWindow, setContextWindow] = useState(0);
  const [account, setAccount] = useState(null);
  const abortRef = useRef(null);
  const runIdRef = useRef("");
  const generationRef = useRef(0);
  const sequenceRef = useRef(0);
  const turnIdRef = useRef("");
  const bottomRef = useRef(null);
  const resolvingRef = useRef(false);
  const busy = BUSY.has(turnState);

  useEffect(() => {
    applyTheme(loadTheme());
  }, []);

  const navigate = useCallback(next => {
    window.location.hash = `/${next}`;
    setPage(next);
  }, []);

  useEffect(() => {
    if (!window.location.hash) window.history.replaceState(null, "", "#/home");
    const sync = () => setPage(initialPage());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const response = await fetch(`${API}/sessions`);
      if (!response.ok) throw new Error(response.statusText);
      const items = await response.json();
      setSessions(items);
      return items;
    } catch (eventError) {
      setError(`无法读取历史会话：${eventError.message}`);
      return [];
    }
  }, []);

  useEffect(() => {
    fetch(`${API}/health`).then(response => response.json()).then(data => {
      if (data.version) setApiVersion(data.version);
      if (data.model) setModelName(data.model);
      if (data.context_window !== undefined) setContextWindow(Math.max(0, Number(data.context_window) || 0));
    }).catch(() => {});
    fetch(`${API}/styles`).then(response => response.json()).then(setStyleGroups).catch(() => {});
    fetch(`${API}/settings/account`).then(response => response.json()).then(setAccount).catch(() => {});
    loadSessions();
  }, [loadSessions]);

  const applyRun = useCallback((run, { replaceMessages = true, adoptRun = false } = {}) => {
    if (!run) return;
    if (run.run_id && !adoptRun && run.run_id !== runIdRef.current) return;
    if (run.run_id && adoptRun) {
      runIdRef.current = run.run_id;
      setRunId(run.run_id);
    }
    if (run.run_id) loadSessions();
    setArtifacts(run.artifacts || {});
    setWorkflowSteps(run.workflow_steps || []);
    if (run.context_size !== undefined) setContextSize(Math.max(0, Number(run.context_size) || 0));
    if (run.window_size !== undefined) setContextWindow(Math.max(0, Number(run.window_size) || 0));
    if (replaceMessages) {
      if (run.messages?.length) {
        setMessages(run.messages.map(item => ({ role: item.role === "assistant" ? "agent" : item.role, content: item.content, steps: [], artifacts: {} })));
      } else if (run.messages) setMessages([]);
    }
    const pending = ["tool_approval", "plan_approval"].includes(run.pending_action?.type) ? run.pending_action : null;
    setPendingApproval(pending);
    setPlanActive(run.plan_mode === true);
    if (run.active_turn?.turn_id) { setActiveTurnId(run.active_turn.turn_id); setTurnState(run.active_turn.status || "running"); }
    else if (pending) setTurnState("waiting_approval");
    else if (run.status === "completed") setTurnState("completed");
    else if (run.status === "failed") setTurnState("failed");
    else if (run.status) setTurnState(["active", "planning", "waiting_user"].includes(run.status) ? "idle" : run.status);
  }, [loadSessions]);

  const refreshRun = useCallback(async (id, opts) => {
    if (!id) return null;
    const generation = generationRef.current;
    const response = await fetch(`${API}/runs/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
    const run = await response.json();
    if (id !== runIdRef.current || generation !== generationRef.current) return null;
    applyRun(run, opts);
    return run;
  }, [applyRun]);

  const scrollDown = () => requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  const updateAgent = useCallback(updater => {
    setMessages(previous => {
      const next = [...previous];
      for (let index = next.length - 1; index >= 0; index -= 1) {
        if (next[index].role === "agent" && next[index].streaming) { next[index] = updater(next[index]); return next; }
      }
      return next;
    });
    scrollDown();
  }, []);

  const handleEvent = useCallback((event, generation) => {
    if (generation !== generationRef.current || !event) return;
    sequenceRef.current = Math.max(sequenceRef.current, Number(event.sequence || 0));
    if (event.turn_id) { setActiveTurnId(event.turn_id); turnIdRef.current = event.turn_id; }
    switch (event.event) {
      case "turn_started": setTurnState("running"); break;
      case "assistant_delta": updateAgent(agent => ({ ...agent, content: (agent.content || "") + (event.text || "") })); break;
      case "reasoning_delta": updateAgent(agent => ({ ...agent, reasoning: (agent.reasoning || "") + (event.text || "") })); break;
      case "provider_call_finished":
        break;
      case "rate_limited":
        if (event.event === "rate_limited") setTurnState("rate_limited");
        break;
      case "tool_started":
        updateAgent(agent => ({ ...agent, steps: [...(agent.steps || []), { key: event.sequence, tool: event.tool || "工具", status: "running" }] }));
        setWorkflowSteps(previous => [...previous, { id: `live-${event.sequence}`, skill: event.tool || "工具", status: "running", started_at: event.timestamp }]);
        break;
      case "tool_result":
        updateAgent(agent => ({ ...agent, steps: [...(agent.steps || []).filter(step => !(step.tool === event.tool && step.status === "running")), { key: event.sequence, tool: event.tool || "工具", status: outcomeStepStatus(event.outcome, event.ok), summary: event.message || "" }], artifacts: { ...(agent.artifacts || {}), ...(event.artifacts || {}) } }));
        setArtifacts(previous => ({ ...previous, ...(event.artifacts || {}) }));
        setWorkflowSteps(previous => {
          const next = [...previous];
          let index = -1;
          for (let cursor = next.length - 1; cursor >= 0; cursor -= 1) {
            if (next[cursor].skill === (event.tool || "工具") && next[cursor].status === "running") {
              index = cursor;
              break;
            }
          }
          const finished = { id: `live-${event.sequence}`, skill: event.tool || "工具", status: outcomeStepStatus(event.outcome, event.ok), outcome: event.outcome || "", summary: event.message || "", finished_at: event.timestamp };
          if (index >= 0) next[index] = { ...next[index], ...finished };
          else next.push(finished);
          return next;
        });
        break;
      case "pause_requested": setTurnState("pause_requested"); break;
      case "turn_paused": setTurnState("paused"); break;
      case "turn_intervened": setTurnState("running"); break;
      case "turn_resumed": setTurnState("running"); break;
      case "approval_required": setTurnState("waiting_approval"); refreshRun(runId).catch(() => {}); break;
      case "turn_finished":
        updateAgent(agent => ({ ...agent, content: event.assistant_message || agent.content || "", reasoning: agent.reasoning || "", artifacts: event.artifacts || agent.artifacts || {}, streaming: false }));
        if (event.context_size !== undefined) setContextSize(Math.max(0, Number(event.context_size) || 0));
        setArtifacts(event.artifacts || {}); setPendingApproval(null); setTurnState("completed"); setActiveTurnId("");
        refreshRun(runId, { replaceMessages: false }).catch(() => {}); break;
      case "turn_failed": updateAgent(agent => ({ ...agent, reasoning: agent.reasoning || "", streaming: false })); setWorkflowSteps(previous => previous.map(step => step.status === "running" ? { ...step, status: "failed" } : step)); setError(event.error || "任务执行失败，但已经完成的成果仍然保留。"); setTurnState("failed"); setActiveTurnId(""); refreshRun(runId, { replaceMessages: false }).catch(() => {}); break;
      case "turn_cancelled":
        updateAgent(agent => {
          const notice = event.message || "任务已停止。已完成的步骤和成果均已保留。";
          const content = (agent.content || "").trim();
          return { ...agent, content: content.includes(notice) ? content : `${content}${content ? "\n\n" : ""}${notice}`, reasoning: agent.reasoning || "", streaming: false };
        });
        setWorkflowSteps(previous => previous.map(step => ["queued", "running"].includes(step.status) ? { ...step, status: "cancelled" } : step));
        setTurnState("cancelled"); setActiveTurnId(""); refreshRun(runId, { replaceMessages: false }).catch(() => {}); break;
      default: break;
    }
  }, [refreshRun, runId, updateAgent]);

  const consume = useCallback(async (response, generation) => {
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "object" ? body.detail.message : body.detail || response.statusText);
    }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done || generation !== generationRef.current) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n"); buffer = lines.pop() || "";
      for (const line of lines) { if (!line.trim()) continue; try { handleEvent(JSON.parse(line), generation); } catch {} }
    }
    if (buffer.trim()) { try { handleEvent(JSON.parse(buffer), generation); } catch {} }
  }, [handleEvent]);

  const reconnectSelectedTurn = useCallback(async (run, generation) => {
    const selectedRunId = run?.run_id;
    const selectedTurnId = run?.active_turn?.turn_id;
    if (!selectedRunId || !selectedTurnId || selectedRunId !== runIdRef.current || generation !== generationRef.current) return;

    const controller = new AbortController();
    abortRef.current = controller; sequenceRef.current = 0; turnIdRef.current = selectedTurnId;
    setActiveTurnId(selectedTurnId); setTurnState(run.active_turn.status || "running");
    setMessages(previous => [...previous, { role: "agent", content: "", reasoning: "", steps: [], artifacts: {}, streaming: true }]);
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(selectedRunId)}/turns/${encodeURIComponent(selectedTurnId)}/events?after=0`, { signal: controller.signal });
      await consume(response, generation);
    } catch (eventError) {
      if (eventError.name !== "AbortError" && selectedRunId === runIdRef.current && generation === generationRef.current) {
        setError(`${eventError.message}。后台任务仍在运行，重新打开会话即可再次连接。`);
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [consume]);

  useEffect(() => {
    if (!runId) return undefined;
    let disposed = false;
    const generation = generationRef.current;
    refreshRun(runId).then(run => {
      if (!disposed && run?.active_turn?.turn_id) reconnectSelectedTurn(run, generation);
    }).catch(eventError => {
      if (!disposed && runId === runIdRef.current && generation === generationRef.current) setError(eventError.message);
    });
    return () => { disposed = true; };
  }, [reconnectSelectedTurn, refreshRun, runId]);

  const startTurn = useCallback(async (text, showUser = true) => {
    const value = text.trim();
    const isIntervention = turnState === "paused";
    if (!runId || !value || (busy && !isIntervention)) return;
    if (apiVersion) {
      try {
        const response = await fetch(`${API}/health`); const health = await response.json();
        if (health.version && health.version !== apiVersion) { setError("后端已经重启，请刷新页面后继续。"); return; }
      } catch { setError("无法连接本地后端。"); return; }
    }
    if (isIntervention) {
      setError("");
      try {
        const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/intervene`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: value }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || response.statusText);
        }
        setMessages(previous => {
          const next = [...previous];
          for (let index = next.length - 1; index >= 0; index -= 1) {
            if (next[index].role === "agent" && next[index].streaming) {
              next[index] = { ...next[index], streaming: false };
              break;
            }
          }
          return [...next, { role: "user", content: value }, { role: "agent", content: "", reasoning: "", steps: [], artifacts: {}, streaming: true }];
        });
        setMessage(""); setTurnState("running"); scrollDown();
      } catch (eventError) {
        setError(eventError.message); setTurnState("paused");
      }
      return;
    }
    const generation = generationRef.current; const controller = new AbortController();
    abortRef.current = controller; sequenceRef.current = 0; setError(""); setTurnState("running"); setPendingApproval(null);
    setMessages(previous => [...previous, ...(showUser ? [{ role: "user", content: value }] : []), { role: "agent", content: "", reasoning: "", steps: [], artifacts: {}, streaming: true }]);
    if (showUser) setMessage(""); scrollDown();
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/turns/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: value }), signal: controller.signal });
      await consume(response, generation);
    } catch (eventError) {
      if (eventError.name !== "AbortError" && generation === generationRef.current) {
        const turnId = turnIdRef.current;
        if (turnId) {
          try {
            const reconnect = await fetch(`${API}/runs/${encodeURIComponent(runId)}/turns/${encodeURIComponent(turnId)}/events?after=${sequenceRef.current}`, { signal: controller.signal });
            await consume(reconnect, generation); return;
          } catch (reconnectError) { if (reconnectError.name === "AbortError") return; }
        }
        setError(`${eventError.message}。已完成的步骤仍然保留，可刷新后继续。`); setTurnState("failed"); updateAgent(agent => ({ ...agent, streaming: false }));
      }
    } finally { if (abortRef.current === controller) abortRef.current = null; }
  }, [apiVersion, busy, consume, runId, turnState, updateAgent]);

  const switchSession = id => {
    if (id === runIdRef.current) return;
    generationRef.current += 1; runIdRef.current = id;
    abortRef.current?.abort(); abortRef.current = null; setRunId(id);
    setMessages([]); setArtifacts({}); setWorkflowSteps([]); setError(""); setPendingApproval(null); setPlanActive(false);
    setContextSize(0);
    setTurnState("idle"); setActiveTurnId(""); sequenceRef.current = 0; turnIdRef.current = "";
  };

  const newRun = useCallback(async () => {
    generationRef.current += 1; const generation = generationRef.current;
    abortRef.current?.abort(); abortRef.current = null;
    setError(""); setMessages([]); setArtifacts({}); setWorkflowSteps([]); setFiles([]); setPendingApproval(null); setPlanActive(false); setTurnState("idle"); setActiveTurnId(""); sequenceRef.current = 0; turnIdRef.current = "";
    try {
      const response = await fetch(`${API}/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: "" }) });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const created = await response.json();
      if (generation !== generationRef.current) return;
      applyRun(created, { adoptRun: true });
    } catch (eventError) { setError(eventError.message); }
  }, [applyRun]);

  useEffect(() => { if (page === "workspace" && !runId) newRun(); }, [newRun, page, runId]);

  const control = async action => {
    if (!runId) return;
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const body = await response.json(); if (body.status) setTurnState(body.status); loadSessions();
    } catch (eventError) { setError(eventError.message); }
  };

  const resolveApproval = async approved => {
    if (!pendingApproval || turnState !== "waiting_approval" || resolvingRef.current) return;
    resolvingRef.current = true;
    setPendingApproval(null); setTurnState("running");
    try {
      if (!approved) {
        const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/reject`, { method: "POST" });
        if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
        const data = await response.json(); applyRun(data);
        if (data.assistant_message) setMessages(previous => [...previous, { role: "agent", content: data.assistant_message, reasoning: "", steps: [], artifacts: data.artifacts || {}, streaming: false }]);
        return;
      }
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/approve`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const data = await response.json(); applyRun(data);
      setMessages(previous => [...previous, { role: "agent", content: data.assistant_message || "操作已完成。", reasoning: "", steps: (data.events || []).filter(event => event.event === "tool_observed").map(event => ({ key: event.sequence, tool: event.skill || "", status: "done", summary: (event.summary || "").slice(0, 200) })), artifacts: data.artifacts || {}, streaming: false }]);
    } catch (eventError) {
      setError(eventError.message); setTurnState("idle");
    } finally {
      resolvingRef.current = false;
    }
  };

  const upload = async event => {
    event.preventDefault();
    if (!runId || !files.length || busy) return;
    const form = event.currentTarget;
    try {
      const formData = new FormData(); files.forEach(file => formData.append("files", file));
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/files`, { method: "POST", body: formData });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const result = await response.json(); applyRun(result); setFiles([]); form.reset();
      const names = Object.values(result.artifacts || {}).map(value => fileName(typeof value === "string" ? value : value.path || "")).filter(Boolean).join("、");
      setMessages(previous => [...previous, { role: "system", content: `已上传：${names}`, steps: [], artifacts: result.artifacts || {} }]);
    } catch (eventError) { setError(eventError.message); }
  };

  const convertFormat = event => {
    const name = event.target.selectedOptions[0]?.text; event.target.value = "";
    if (name) startTurn(`请将上传文档中的参考文献转换为 ${name} 格式`, false);
  };

  const deleteSessions = async () => {
    if (!deleteMode) { setDeleteMode(true); setSelectedSessions(new Set()); return; }
    if (!selectedSessions.size) { setDeleteMode(false); return; }
    const ids = [...selectedSessions];
    const results = await Promise.all(ids.map(id =>
      fetch(`${API}/runs/${encodeURIComponent(id)}/delete`, { method: "POST" }).then(r => r.ok, () => false)
    ));
    if (results.every(Boolean)) {
      if (ids.includes(runId)) {
        generationRef.current += 1; runIdRef.current = "";
        setRunId(""); setMessages([]);
      }
      setSelectedSessions(new Set()); setDeleteMode(false); loadSessions();
    }
  };

  const deleteMessages = async () => {
    if (msgDeleteMode && selectedMsgs.size > 0) {
      const indices = [...selectedMsgs].sort((left, right) => right - left);
      const results = await Promise.all(indices.map(index =>
        fetch(`${API}/runs/${encodeURIComponent(runId)}/trim/${index}`, { method: "POST" }).then(r => r.ok, () => false)
      ));
      if (results.every(Boolean)) {
        setMessages(previous => previous.filter((_, index) => !selectedMsgs.has(index)));
        setSelectedMsgs(new Set()); setMsgDeleteMode(false);
      }
    } else { setMsgDeleteMode(value => !value); setSelectedMsgs(new Set()); }
  };

  const openTask = id => {
    if (id !== runId) switchSession(id);
    navigate("workspace");
  };

  return (
    <div className="app-shell">
      <TopNav page={page} onNavigate={navigate} account={account} />
      <div className="page-transition" key={page}>
        {page === "home" && <HomePage onStart={() => navigate("workspace")} />}
        {page === "workspace" && <WorkspacePage
          runId={runId} sessions={sessions} selectedSessions={selectedSessions} setSelectedSessions={setSelectedSessions}
          deleteMode={deleteMode} setDeleteMode={setDeleteMode} onDeleteSessions={deleteSessions} onNewRun={newRun}
              onSwitchSession={switchSession} turnState={turnState} modelName={modelName} contextSize={contextSize} contextWindow={contextWindow} control={control} messages={messages} msgDeleteMode={msgDeleteMode}
          selectedMsgs={selectedMsgs} setSelectedMsgs={setSelectedMsgs} onDeleteMessages={deleteMessages}
          pendingApproval={pendingApproval} resolveApproval={resolveApproval} error={error} files={files} setFiles={setFiles}
          upload={upload} styleGroups={styleGroups} convertFormat={convertFormat} planActive={planActive} startTurn={startTurn}
          message={message} setMessage={setMessage} busy={busy} activeTurnId={activeTurnId} bottomRef={bottomRef}
              artifacts={artifacts} workflowSteps={workflowSteps}
        />}
        {page === "tasks" && <TaskCenterPage api={API} sessions={sessions} onOpen={openTask} onRefresh={loadSessions} />}
        {page === "settings" && <SettingsPage api={API} onAccountChange={setAccount} />}
      </div>
    </div>
  );
}
