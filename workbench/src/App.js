import { useCallback, useEffect, useRef, useState } from "react";
import TopNav, { BrandMark } from "./components/TopNav";
import ApprovalDock from "./components/ApprovalDock";
import HomePage from "./pages/HomePage";
import SettingsPage from "./pages/SettingsPage";
import TaskCenterPage from "./pages/TaskCenterPage";

const API = "http://127.0.0.1:8877";
const BUSY = new Set(["running", "pause_requested", "paused", "waiting_approval", "rate_limited"]);

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

function artifactEntries(value) {
  return Object.entries(value || {}).map(([name, item]) => {
    const path = typeof item === "string" ? item : item?.path || "";
    return [name, path];
  }).filter(([, path]) => /\.(docx|pdf)$/i.test(path));
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).pop() || path;
}

function WorkspacePage({
  runId, sessions, selectedSessions, setSelectedSessions, deleteMode, setDeleteMode,
  onDeleteSessions, onNewRun, onSwitchSession, turnState, modelName, tokenUsage, tokenLimit,
  control, messages, msgDeleteMode, selectedMsgs, setSelectedMsgs, onDeleteMessages,
  pendingApproval, resolveApproval, error, files, setFiles, upload, styleGroups,
  convertFormat, planActive, startTurn, message, setMessage, busy, activeTurnId, bottomRef,
}) {
  const activeSession = sessions.find(session => session.run_id === runId);
  const usagePercent = Math.min(100, tokenUsage / Math.max(1, tokenLimit) * 100);

  return (
    <main className="workspace-page page-frame">
      <aside className="conversation-sidebar">
        <button onClick={onNewRun} className="new-session-button"><span>＋</span>新建会话</button>
        <button className={`delete-session-button ${deleteMode ? "active" : ""}`} onClick={onDeleteSessions}>
          <span>⌫</span>{deleteMode && selectedSessions.size ? `删除会话（${selectedSessions.size}）` : "删除会话"}
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
                <span className="session-icon">▤</span>
                <span className="session-body"><strong>{session.title || "新会话"}</strong><small>{String(session.updated_at || session.created_at || "").slice(0, 10)}</small></span>
                {deleteMode && <span className={`selection-dot ${selected ? "checked" : ""}`}>{selected ? "✓" : ""}</span>}
              </button>
            );
          })}
          {!sessions.length && <div className="sidebar-empty"><span>⌁</span><p>还没有历史会话</p></div>}
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
            {modelName && <div className="model-usage"><strong>{modelName}</strong><span><i style={{ width: `${usagePercent}%` }} /></span><small>{(tokenUsage / 1000).toFixed(1)}k / {(tokenLimit / 1000).toFixed(0)}k</small></div>}
            <button type="button" onClick={() => control("pause")} disabled={turnState !== "running"}>Ⅱ 暂停</button>
            <button type="button" onClick={() => control("resume")} disabled={!(["paused", "rate_limited"].includes(turnState))}>▶ 恢复</button>
            <button type="button" className="danger-soft" onClick={() => control("cancel")} disabled={!BUSY.has(turnState)}>× 取消</button>
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
                    {(item.steps || []).map(step => <div key={step.key} className={`execution-step ${step.status}`}><span>{step.status === "running" ? "…" : step.status === "failed" ? "×" : "✓"}</span><p><strong>{step.tool}</strong>{step.summary && <small>{step.summary}</small>}</p></div>)}
                  </div>}
                  {item.content && <div className="message-content">{item.content}</div>}
                  {item.streaming && !item.content && !(item.steps || []).length && <div className="thinking-indicator"><i /><i /><i /><span>正在理解任务</span></div>}
                  {(item.calls || []).length > 0 && <details className="call-details"><summary>模型调用 {(item.calls || []).length} 次</summary>{item.calls.map(call => <div key={call.call_id || `${call.operation}-${call.attempt}`}><span>{call.operation}</span><span>第 {call.attempt} 次</span><span>{call.status}</span></div>)}</details>}
                  {artifactEntries(item.artifacts).length > 0 && <div className="artifact-list">{artifactEntries(item.artifacts).map(([name, path]) => <span className="artifact-chip" key={name}><i>▤</i><span>{fileName(path)}</span></span>)}</div>}
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
              <label htmlFor="workspace-files" className="tool-button">⌕ 上传文件</label>
              <input id="workspace-files" type="file" multiple onChange={event => setFiles(Array.from(event.target.files || []))} disabled={busy} />
              {files.length > 0 && <button className="upload-ready" disabled={!runId || busy}>上传（{files.length}）</button>}
            </form>
            <select className="format-select" onChange={convertFormat} disabled={!runId || busy} defaultValue="">
              <option value="" disabled>格式转换</option>
              {styleGroups.map(group => <optgroup key={group.group} label={group.group}>{group.items.map(style => <option key={style.key} value={style.key}>{style.name}</option>)}</optgroup>)}
            </select>
            <button className={`tool-button ${planActive ? "active" : ""}`} onClick={() => startTurn("/plan", false)} disabled={busy}>{planActive ? "✓ 计划模式" : "▣ 计划模式"}</button>
            <button className={`tool-button ${msgDeleteMode ? "active danger" : ""}`} onClick={onDeleteMessages}>{msgDeleteMode ? (selectedMsgs.size ? `确认删除（${selectedMsgs.size}）` : "选择消息") : "⌫ 删除消息"}</button>
          </div>
          <form onSubmit={event => { event.preventDefault(); startTurn(message, true); }} className="message-composer">
            <textarea
              value={message}
              onChange={event => setMessage(event.target.value)}
              onKeyDown={event => { if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); startTurn(message, true); } }}
              disabled={busy}
              placeholder="描述你希望 Agent 完成的科研任务…"
              rows={3}
            />
            <button disabled={!runId || !message.trim() || busy} className="send-button"><span>发送</span><i>➤</i></button>
          </form>
          <div className="composer-meta"><span>Ctrl + Enter 发送</span>{activeTurnId && <span>Turn {activeTurnId.slice(0, 8)}</span>}</div>
        </section>
      </section>
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
  const [error, setError] = useState("");
  const [files, setFiles] = useState([]);
  const [turnState, setTurnState] = useState("idle");
  const [activeTurnId, setActiveTurnId] = useState("");
  const [pendingApproval, setPendingApproval] = useState(null);
  const [planActive, setPlanActive] = useState(false);
  const [styleGroups, setStyleGroups] = useState([]);
  const [apiVersion, setApiVersion] = useState("");
  const [modelName, setModelName] = useState("");
  const [tokenUsage, setTokenUsage] = useState(0);
  const [tokenLimit, setTokenLimit] = useState(1000000);
  const [account, setAccount] = useState(null);
  const abortRef = useRef(null);
  const generationRef = useRef(0);
  const sequenceRef = useRef(0);
  const turnIdRef = useRef("");
  const bottomRef = useRef(null);
  const resolvingRef = useRef(false);
  const busy = BUSY.has(turnState);

  useEffect(() => {
    try {
      const colors = JSON.parse(localStorage.getItem("research-agent-theme-colors") || "null");
      if (!colors) return;
      const root = document.documentElement;
      const variables = { page: "--page-bg", surface: "--cream-0", soft: "--sage-1", accent: "--sage-4", strong: "--sage-5", text: "--cocoa", muted: "--muted", line: "--line" };
      Object.entries(variables).forEach(([key, variable]) => colors[key] && root.style.setProperty(variable, colors[key]));
    } catch {}
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
    }).catch(() => {});
    fetch(`${API}/styles`).then(response => response.json()).then(setStyleGroups).catch(() => {});
    fetch(`${API}/settings/account`).then(response => response.json()).then(setAccount).catch(() => {});
    loadSessions();
  }, [loadSessions]);

  const applyRun = useCallback((run, { replaceMessages = true } = {}) => {
    if (!run) return;
    if (run.run_id) { setRunId(run.run_id); loadSessions(); }
    setArtifacts(run.artifacts || {});
    if (run.context_size !== undefined) setTokenUsage(run.context_size);
    if (run.window_size) setTokenLimit(run.window_size);
    if (replaceMessages) {
      if (run.messages?.length) {
        setMessages(run.messages.map(item => ({ role: item.role === "assistant" ? "agent" : item.role, content: item.content, steps: [], calls: [], artifacts: {} })));
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
    const response = await fetch(`${API}/runs/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
    const run = await response.json();
    applyRun(run, opts);
    return run;
  }, [applyRun]);

  useEffect(() => { if (runId) refreshRun(runId).catch(() => {}); }, [runId, refreshRun]);

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
      case "provider_call_started":
        updateAgent(agent => ({ ...agent, calls: [...(agent.calls || []), { call_id: event.call_id, operation: event.operation || "模型调用", attempt: event.attempt || 1, status: "running", started_at: event.timestamp }] })); break;
      case "provider_call_finished":
      case "rate_limited":
        updateAgent(agent => ({ ...agent, calls: (agent.calls || []).map(call => call.call_id === event.call_id ? { ...call, status: event.status || event.event, usage: event.usage || {}, error: event.error || "" } : call) }));
        if (event.event === "rate_limited") setTurnState("rate_limited");
        break;
      case "tool_started":
        updateAgent(agent => ({ ...agent, steps: [...(agent.steps || []), { key: event.sequence, tool: event.tool || "工具", status: "running" }] })); break;
      case "tool_result":
        updateAgent(agent => ({ ...agent, steps: [...(agent.steps || []).filter(step => !(step.tool === event.tool && step.status === "running")), { key: event.sequence, tool: event.tool || "工具", status: event.ok === false ? "failed" : "done", summary: event.message || "" }], artifacts: { ...(agent.artifacts || {}), ...(event.artifacts || {}) } }));
        setArtifacts(previous => ({ ...previous, ...(event.artifacts || {}) }));
        break;
      case "pause_requested": setTurnState("pause_requested"); break;
      case "turn_paused": setTurnState("paused"); break;
      case "turn_resumed": setTurnState("running"); break;
      case "approval_required": setTurnState("waiting_approval"); refreshRun(runId).catch(() => {}); break;
      case "turn_finished":
        updateAgent(agent => ({ ...agent, content: agent.content || event.assistant_message || "", artifacts: event.artifacts || agent.artifacts || {}, streaming: false }));
        setArtifacts(event.artifacts || {}); setPendingApproval(null); setTurnState("completed"); setActiveTurnId("");
        if (event.context_size !== undefined) setTokenUsage(event.context_size);
        refreshRun(runId, { replaceMessages: false }).catch(() => {}); break;
      case "turn_failed": updateAgent(agent => ({ ...agent, streaming: false })); setError(event.error || "任务执行失败，但已经完成的成果仍然保留。"); setTurnState("failed"); setActiveTurnId(""); break;
      case "turn_cancelled": updateAgent(agent => ({ ...agent, streaming: false })); setTurnState("cancelled"); setActiveTurnId(""); break;
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

  const startTurn = useCallback(async (text, showUser = true) => {
    const value = text.trim();
    if (!runId || !value || busy) return;
    if (apiVersion) {
      try {
        const response = await fetch(`${API}/health`); const health = await response.json();
        if (health.version && health.version !== apiVersion) { setError("后端已经重启，请刷新页面后继续。"); return; }
      } catch { setError("无法连接本地后端。"); return; }
    }
    const generation = generationRef.current; const controller = new AbortController();
    abortRef.current = controller; sequenceRef.current = 0; setError(""); setTurnState("running"); setPendingApproval(null);
    setMessages(previous => [...previous, ...(showUser ? [{ role: "user", content: value }] : []), { role: "agent", content: "", steps: [], calls: [], artifacts: {}, streaming: true }]);
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
  }, [apiVersion, busy, consume, runId, updateAgent]);

  const switchSession = id => {
    if (id === runId || busy) return;
    abortRef.current?.abort(); abortRef.current = null; setRunId(id);
    setMessages([]); setArtifacts({}); setError(""); setPendingApproval(null); setPlanActive(false);
    setTurnState("idle"); setActiveTurnId(""); sequenceRef.current = 0; turnIdRef.current = ""; generationRef.current += 1;
    refreshRun(id).catch(eventError => setError(eventError.message));
  };

  const newRun = useCallback(async () => {
    const oldRun = runId; generationRef.current += 1; abortRef.current?.abort(); abortRef.current = null;
    if (oldRun) fetch(`${API}/runs/${encodeURIComponent(oldRun)}/cancel`, { method: "POST" }).catch(() => {});
    setError(""); setMessages([]); setArtifacts({}); setFiles([]); setPendingApproval(null); setPlanActive(false); setTurnState("idle"); setActiveTurnId(""); sequenceRef.current = 0; turnIdRef.current = "";
    try {
      const response = await fetch(`${API}/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: "" }) });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      applyRun(await response.json());
    } catch (eventError) { setError(eventError.message); }
  }, [applyRun, runId]);

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
        if (data.assistant_message) setMessages(previous => [...previous, { role: "agent", content: data.assistant_message, steps: [], calls: [], artifacts: data.artifacts || {}, streaming: false }]);
        return;
      }
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/approve`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const data = await response.json(); applyRun(data);
      setMessages(previous => [...previous, { role: "agent", content: data.assistant_message || "操作已完成。", steps: (data.events || []).filter(event => event.event === "tool_observed").map(event => ({ key: event.sequence, tool: event.skill || "", status: "done", summary: (event.summary || "").slice(0, 200) })), calls: [], artifacts: data.artifacts || {}, streaming: false }]);
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
      setMessages(previous => [...previous, { role: "system", content: `已上传：${names}`, steps: [], calls: [], artifacts: result.artifacts || {} }]);
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
    await Promise.all(ids.map(id => fetch(`${API}/runs/${encodeURIComponent(id)}/delete`, { method: "POST" }).catch(() => {})));
    if (ids.includes(runId)) { setRunId(""); setMessages([]); }
    setSelectedSessions(new Set()); setDeleteMode(false); loadSessions();
  };

  const deleteMessages = async () => {
    if (msgDeleteMode && selectedMsgs.size > 0) {
      const indices = [...selectedMsgs].sort((left, right) => right - left);
      await Promise.all(indices.map(index => fetch(`${API}/runs/${encodeURIComponent(runId)}/trim/${index}`, { method: "POST" }).catch(() => {})));
      setMessages(previous => previous.filter((_, index) => !selectedMsgs.has(index))); setSelectedMsgs(new Set()); setMsgDeleteMode(false);
    } else { setMsgDeleteMode(value => !value); setSelectedMsgs(new Set()); }
  };

  const openTask = id => {
    if (busy && id !== runId) { navigate("workspace"); setError("当前任务仍在运行，请先暂停或结束后再切换会话。"); return; }
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
          onSwitchSession={switchSession} turnState={turnState} modelName={modelName} tokenUsage={tokenUsage}
          tokenLimit={tokenLimit} control={control} messages={messages} msgDeleteMode={msgDeleteMode}
          selectedMsgs={selectedMsgs} setSelectedMsgs={setSelectedMsgs} onDeleteMessages={deleteMessages}
          pendingApproval={pendingApproval} resolveApproval={resolveApproval} error={error} files={files} setFiles={setFiles}
          upload={upload} styleGroups={styleGroups} convertFormat={convertFormat} planActive={planActive} startTurn={startTurn}
          message={message} setMessage={setMessage} busy={busy} activeTurnId={activeTurnId} bottomRef={bottomRef}
        />}
        {page === "tasks" && <TaskCenterPage api={API} sessions={sessions} onOpen={openTask} onRefresh={loadSessions} />}
        {page === "settings" && <SettingsPage api={API} onAccountChange={setAccount} />}
      </div>
    </div>
  );
}
