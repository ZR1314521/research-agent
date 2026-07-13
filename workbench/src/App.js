import { useCallback, useEffect, useRef, useState } from "react";

const API = "http://127.0.0.1:8877";
const BUSY = new Set(["running", "pause_requested", "paused", "waiting_approval", "rate_limited"]);

export default function App() {
  const [runId, setRunId] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedSessions, setSelectedSessions] = useState(new Set());
  const [deleteMode, setDeleteMode] = useState(false);
  const [msgDeleteMode, setMsgDeleteMode] = useState(false);
  const [selectedMsgs, setSelectedMsgs] = useState(new Set());
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupProvider, setSetupProvider] = useState("");
  const [setupKey, setSetupKey] = useState("");
  const [setupUrl, setSetupUrl] = useState("");
  const [setupModel, setSetupModel] = useState("");
  const [setupCtx, setSetupCtx] = useState("1000000");
  const [setupTimeout, setSetupTimeout] = useState("300");
  const [setupConcurrency, setSetupConcurrency] = useState("1");
  const [setupPresets, setSetupPresets] = useState([]);
  const [setupAdvanced, setSetupAdvanced] = useState(false);
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
  const abortRef = useRef(null);

  useEffect(() => {
    fetch(`${API}/health`).then(r => r.json()).then(d => {
      if (d.version) setApiVersion(d.version);
      if (d.model) setModelName(d.model);
    }).catch(() => {});
  }, []);
  const generationRef = useRef(0);
  const sequenceRef = useRef(0);
  const turnIdRef = useRef("");
  const bottomRef = useRef(null);

  const busy = BUSY.has(turnState);
  const scrollDown = () => requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));

  useEffect(() => {
    fetch(`${API}/styles`).then(r => r.json()).then(setStyleGroups).catch(() => {});
  }, []);

  const applyRun = useCallback((run) => {
    if (!run) return;
    if (run.run_id) {
      setRunId(run.run_id);
      fetch(`${API}/sessions`).then(r => r.json()).then(setSessions).catch(() => {});
    }
    setArtifacts(run.artifacts || {});
    if (run.token_usage !== undefined) setTokenUsage(run.token_usage);
    if (run.token_limit) setTokenLimit(run.token_limit);
    if (run.messages?.length) {
      setMessages(run.messages.map(m => ({ role: m.role, content: m.content, steps: [], calls: [], artifacts: {} })));
    }
    setPendingApproval(["tool_approval", "plan_approval"].includes(run.pending_action?.type) ? run.pending_action : null);
    setPlanActive(run.plan_mode === true);
    if (run.active_turn?.turn_id) {
      setActiveTurnId(run.active_turn.turn_id);
      setTurnState(run.active_turn.status || "running");
    }
  }, []);

  const refreshRun = useCallback(async (id) => {
    if (!id) return null;
    const response = await fetch(`${API}/runs/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
    const run = await response.json();
    applyRun(run);
    return run;
  }, [applyRun]);

  useEffect(() => {
    if (runId) refreshRun(runId).catch(() => {});
  }, [runId, refreshRun]);

  const updateAgent = useCallback((updater) => {
    setMessages(previous => {
      const next = [...previous];
      for (let index = next.length - 1; index >= 0; index -= 1) {
        if (next[index].role === "agent" && next[index].streaming) {
          next[index] = updater(next[index]);
          return next;
        }
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
      case "turn_started":
        setTurnState("running");
        break;
      case "assistant_delta":
        updateAgent(agent => ({ ...agent, content: (agent.content || "") + (event.text || "") }));
        break;
      case "provider_call_started":
        updateAgent(agent => ({
          ...agent,
          calls: [...(agent.calls || []), {
            call_id: event.call_id, operation: event.operation || "provider call",
            attempt: event.attempt || 1, status: "running", started_at: event.timestamp,
          }],
        }));
        break;
      case "provider_call_finished":
      case "rate_limited":
        updateAgent(agent => ({
          ...agent,
          calls: (agent.calls || []).map(call => call.call_id === event.call_id
            ? { ...call, status: event.status || event.event, usage: event.usage || {}, error: event.error || "" }
            : call),
        }));
        if (event.event === "rate_limited") setTurnState("rate_limited");
        break;
      case "tool_started":
        updateAgent(agent => ({
          ...agent,
          steps: [...(agent.steps || []), { key: event.sequence, tool: event.tool || "tool", status: "running" }],
        }));
        break;
      case "tool_result":
        updateAgent(agent => ({
          ...agent,
          steps: [...(agent.steps || []).filter(step => !(step.tool === event.tool && step.status === "running")), {
            key: event.sequence, tool: event.tool || "tool", status: event.ok === false ? "failed" : "done",
            summary: event.message || "",
          }],
          artifacts: { ...(agent.artifacts || {}), ...(event.artifacts || {}) },
        }));
        setArtifacts(previous => ({ ...previous, ...(event.artifacts || {}) }));
        break;
      case "pause_requested":
        setTurnState("pause_requested");
        break;
      case "turn_paused":
        setTurnState("paused");
        break;
      case "turn_resumed":
        setTurnState("running");
        break;
      case "approval_required":
        setTurnState("waiting_approval");
        refreshRun(runId).catch(() => {});
        break;
      case "turn_finished":
        updateAgent(agent => ({
          ...agent,
          content: agent.content || event.assistant_message || "",
          artifacts: event.artifacts || agent.artifacts || {},
          streaming: false,
        }));
        setArtifacts(event.artifacts || {});
        setPendingApproval(null);
        setTurnState("completed");
        setActiveTurnId("");
        refreshRun(runId).catch(() => {});
        break;
      case "turn_failed":
        updateAgent(agent => ({ ...agent, streaming: false }));
        setError(event.error || "任务执行失败，但已经完成的成果仍然保留。");
        setTurnState("failed");
        setActiveTurnId("");
        break;
      case "turn_cancelled":
        updateAgent(agent => ({ ...agent, streaming: false }));
        setTurnState("cancelled");
        setActiveTurnId("");
        break;
      default:
        break;
    }
  }, [refreshRun, runId, updateAgent]);

  const consume = useCallback(async (response, generation) => {
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "object" ? body.detail.message : body.detail || response.statusText);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done || generation !== generationRef.current) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try { handleEvent(JSON.parse(line), generation); } catch {}
      }
    }
    if (buffer.trim()) {
      try { handleEvent(JSON.parse(buffer), generation); } catch {}
    }
  }, [handleEvent]);

  const startTurn = useCallback(async (text, showUser = true) => {
    const value = text.trim();
    if (!runId || !value || busy) return;
    // Version check before sending
    if (apiVersion) {
      try {
        const h = await fetch(`${API}/health`);
        const hd = await h.json();
        if (hd.version && hd.version !== apiVersion) {
          setError("Backend restarted. Please refresh the page.");
          return;
        }
      } catch { setError("Backend unreachable."); return; }
    }
    const generation = generationRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    sequenceRef.current = 0;
    setError("");
    setTurnState("running");
    setPendingApproval(null);
    setMessages(previous => [
      ...previous,
      ...(showUser ? [{ role: "user", content: value }] : []),
      { role: "agent", content: "", steps: [], calls: [], artifacts: {}, streaming: true },
    ]);
    if (showUser) setMessage("");
    scrollDown();
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/turns/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: value }),
        signal: controller.signal,
      });
      await consume(response, generation);
    } catch (eventError) {
      if (eventError.name !== "AbortError" && generation === generationRef.current) {
        const turnId = turnIdRef.current;
        if (turnId) {
          try {
            const reconnect = await fetch(
              `${API}/runs/${encodeURIComponent(runId)}/turns/${encodeURIComponent(turnId)}/events?after=${sequenceRef.current}`,
              { signal: controller.signal },
            );
            await consume(reconnect, generation);
            return;
          } catch (reconnectError) {
            if (reconnectError.name === "AbortError") return;
          }
        }
        setError(`${eventError.message}。已完成的步骤仍然保留，可刷新后继续。`);
        setTurnState("failed");
        updateAgent(agent => ({ ...agent, streaming: false }));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [busy, consume, runId, updateAgent]);

  const switchSession = (id) => {
    if (id === runId || busy) return;
    abortRef.current?.abort();
    abortRef.current = null;
    setRunId(id);
    setMessages([]); setArtifacts({}); setError(""); setPendingApproval(null);
    setPlanActive(false); setTurnState("idle"); setActiveTurnId(""); sequenceRef.current = 0; turnIdRef.current = "";
    generationRef.current += 1;
    refreshRun(id).catch(() => {});
  };

  const newRun = useCallback(async () => {
    const oldRun = runId;
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    if (oldRun) fetch(`${API}/runs/${encodeURIComponent(oldRun)}/cancel`, { method: "POST" }).catch(() => {});
    setError(""); setMessages([]); setArtifacts({}); setFiles([]); setPendingApproval(null);
    setPlanActive(false); setTurnState("idle"); setActiveTurnId(""); sequenceRef.current = 0; turnIdRef.current = "";
    try {
      const response = await fetch(`${API}/runs`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: "" }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      applyRun(await response.json());
    } catch (eventError) { setError(eventError.message); }
  }, [applyRun, runId]);

  useEffect(() => { if (!runId) newRun(); }, [newRun, runId]);

  const control = async (action) => {
    if (!runId) return;
    try {
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const body = await response.json();
      if (body.status) setTurnState(body.status);
    } catch (eventError) { setError(eventError.message); }
  };

  const resolveApproval = async (approved) => {
    if (!pendingApproval || turnState !== "waiting_approval") return;
    setPendingApproval(null);
    setTurnState("running");
    if (!approved) {
      try {
        await fetch(`${API}/runs/${encodeURIComponent(runId)}/reject`, { method: "POST" });
      } catch {}
      applyRun({ pending_action: null });
      return;
    }
    try {
      const r = await fetch(`${API}/runs/${encodeURIComponent(runId)}/approve`, { method: "POST" });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      const data = await r.json();
      applyRun(data);
      setMessages(prev => [...prev, {
        role: "agent", content: data.message || "Done.",
        steps: (data.events || []).filter(e => e.event === "tool_observed").map(e => ({ key: e.sequence, tool: e.skill || "", status: "done", summary: (e.summary || "").slice(0, 200) })),
        calls: [], artifacts: data.artifacts || {}, streaming: false,
      }]);
    } catch (eventError) { setError(eventError.message); setTurnState("idle"); }
  };

  const upload = async (event) => {
    event.preventDefault();
    if (!runId || !files.length || busy) return;
    const form = event.currentTarget;
    try {
      const formData = new FormData(); const count = files.length; files.forEach(file => formData.append("files", file));
      const response = await fetch(`${API}/runs/${encodeURIComponent(runId)}/files`, { method: "POST", body: formData });
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      const result = await response.json();
      applyRun(result); setFiles([]); form.reset();
      const names = Object.values(result.artifacts || {}).map(v => typeof v === "string" ? v.split("/").pop().split("\\").pop() : v.path?.split("/").pop()?.split("\\").pop() || "").filter(Boolean).join(", ");
      const doc = result.artifacts?.latest_document || result.artifacts?.uploaded_document_1 || "";
      const path = typeof doc === "string" ? doc : doc.path || "";
      setMessages(prev => [...prev, { role: "system", content: `Uploaded: ${names}`, steps: [], calls: [], artifacts: result.artifacts || {} }]);
    } catch (eventError) { setError(eventError.message); }
  };

  const convertFormat = (event) => {
    const name = event.target.selectedOptions[0]?.text;
    event.target.value = "";
    if (name) startTurn(`请将上传文档中的参考文献转换为 ${name} 格式`, false);
  };

  const artifactEntries = (value) => Object.entries(value || {}).filter(([, item]) => {
    if (!item) return false;
    const p = (item.path || "").toLowerCase();
    return p.endsWith(".docx") || p.endsWith(".pdf");
  });

  return (
    <div className="chat-app">
      <aside className="sidebar">
        <button onClick={newRun} className="new-run-btn">+ New</button>
        <button className={`del-sessions-btn ${deleteMode ? "del-active" : ""}`} onClick={() => {
          if (deleteMode && selectedSessions.size > 0) {
            const ids = [...selectedSessions];
            Promise.all(ids.map(id => fetch(`${API}/runs/${encodeURIComponent(id)}/delete`, { method: "POST" })))
              .then(() => { setSelectedSessions(new Set()); setDeleteMode(false); fetch(`${API}/sessions`).then(r => r.json()).then(setSessions); });
            if (ids.includes(runId)) { setRunId(""); setMessages([]); }
          } else {
            setDeleteMode(!deleteMode);
            setSelectedSessions(new Set());
          }
        }}>{deleteMode ? (selectedSessions.size > 0 ? `Delete (${selectedSessions.size})` : "Delete") : "Select to delete"}</button>
        <div className="session-list">
          {sessions.map(s => {
            const sel = selectedSessions.has(s.run_id);
            const cls = `session-item ${s.run_id === runId ? "active" : ""} ${sel ? "selected" : ""}`;
            return (
            <div key={s.run_id} className={cls} onClick={() => {
              if (deleteMode) {
                const next = new Set(selectedSessions);
                sel ? next.delete(s.run_id) : next.add(s.run_id);
                setSelectedSessions(next);
              } else {
                switchSession(s.run_id);
              }
            }}>
              {deleteMode && <span className="session-cb">{sel ? "[x]" : "[ ]"}</span>}
              <span className="session-body">
                <span className="session-title">{s.title || "new session"}</span>
                <span className="session-meta">{s.created_at?.slice(0,10) || ""}</span>
              </span>
            </div>
          )})}
        </div>
      </aside>
      <div className="chat-main">
        <header className="chat-header">
          <div><h1>Research Agent</h1><span className={`status status-${turnState}`}>{turnState}</span></div>
          <button className="setup-btn" onClick={async () => {
            try { const r = await fetch(`${API}/setup/presets`); setSetupPresets(await r.json()); } catch {}
            setSetupOpen(true);
          }}>Setup</button>
        </header>

      <main className="chat-history">
        {messages.length === 0 && <div className="empty-state">直接描述你想得到的科研结果。Agent 会在同一条执行流中调用工具并返回成果。</div>}
        {messages.map((item, index) => (
          <div key={index} className={`msg-row ${item.role === "user" ? "msg-row-right" : "msg-row-left"}`}>
            {msgDeleteMode && item.role === "agent" && <span className={`msg-sel ${selectedMsgs.has(index) ? "msg-sel-on" : ""}`} onClick={() => { const next = new Set(selectedMsgs); selectedMsgs.has(index) ? next.delete(index) : next.add(index); setSelectedMsgs(next); }} />}
            <article className={`chat-msg ${item.role} ${selectedMsgs.has(index) ? "msg-selected" : ""}`} onClick={() => { if (!msgDeleteMode) return; const next = new Set(selectedMsgs); selectedMsgs.has(index) ? next.delete(index) : next.add(index); setSelectedMsgs(next); }}>
            <div className="msg-label">{item.role === "user" ? "You" : "Agent"}</div>
            {(item.steps || []).length > 0 && <div className="msg-steps">
              {item.steps.map(step => <div key={step.key} className={`msg-step ${step.status}`}>
                <span className="step-dot">{step.status === "running" ? "[…]" : step.status === "failed" ? "[×]" : "[✓]"}</span>
                <span>{step.tool}{step.summary ? `：${step.summary}` : ""}</span>
              </div>)}
            </div>}
            {item.content && <div className="msg-content">{item.content}</div>}
            {item.streaming && !item.content && (item.steps || []).length === 0 && <div className="stream-wait">正在理解任务…</div>}
            {(item.calls || []).length > 0 && <details className="call-stats">
              <summary>模型调用 {(item.calls || []).length} 次</summary>
              {(item.calls || []).map(call => <div key={call.call_id || `${call.operation}-${call.attempt}`} className="call-row">
                <span>{call.operation}</span><span>第 {call.attempt} 次</span><span>{call.status}</span>
              </div>)}
            </details>}
            {artifactEntries(item.artifacts).length > 0 && <div className="msg-files">
              {artifactEntries(item.artifacts).map(([name, value]) => <span className="file-tag" key={name}>{name}：{value.path || value}</span>)}
            </div>}
          </article>
            {msgDeleteMode && item.role === "user" && <span className={`msg-sel ${selectedMsgs.has(index) ? "msg-sel-on" : ""}`} onClick={() => { const next = new Set(selectedMsgs); selectedMsgs.has(index) ? next.delete(index) : next.add(index); setSelectedMsgs(next); }} />}
          </div>
        ))}
        <div ref={bottomRef} />
      </main>

      {error && <div className="chat-error">{error}</div>}
      {pendingApproval && <div className="approval-banner">{pendingApproval.summary || "这一步需要你的确认后才能继续。"}</div>}

      {modelName && <div className="usage-bar">
        <span className="usage-model">{modelName}</span>
        <span className="usage-bar-track"><span className="usage-bar-fill" style={{width: `${Math.min(100, tokenUsage / Math.max(1, tokenLimit) * 100)}%`}} /></span>
        <span className="usage-text">{Math.round(tokenUsage / Math.max(1, tokenLimit) * 100)}% ({(tokenUsage/1000).toFixed(0)}k/{tokenLimit/1000}k)</span>
      </div>}
      <section className="chat-input-area">
        <div className="chat-toolbar">
          <form onSubmit={upload} className="upload-form">
            <input type="file" multiple onChange={event => setFiles(Array.from(event.target.files || []))} disabled={busy} />
            <button disabled={!runId || !files.length || busy}>Upload ({files.length})</button>
          </form>
          <select className="fmt-select" onChange={convertFormat} disabled={!runId || busy} defaultValue="">
            <option value="" disabled>Convert</option>
            {styleGroups.map(group => <optgroup key={group.group} label={group.group}>
              {group.items.map(style => <option key={style.key} value={style.key}>{style.name}</option>)}
            </optgroup>)}
          </select>
          <button className={`msg-del-btn ${msgDeleteMode ? "del-active" : ""}`} onClick={async () => {
            if (msgDeleteMode && selectedMsgs.size > 0) {
              const indices = [...selectedMsgs].sort((a,b) => b-a);
              await Promise.all(indices.map(i => fetch(`${API}/runs/${encodeURIComponent(runId)}/trim/${i}`, { method: "POST" }).catch(() => {})));
              setMessages(prev => prev.filter((_, i) => !selectedMsgs.has(i)));
              setSelectedMsgs(new Set()); setMsgDeleteMode(false);
            } else {
              setMsgDeleteMode(!msgDeleteMode); setSelectedMsgs(new Set());
            }
          }}>{msgDeleteMode ? (selectedMsgs.size > 0 ? `Confirm (${selectedMsgs.size})` : "Delete") : "Delete"}</button>
        </div>
        <form onSubmit={event => { event.preventDefault(); startTurn(message, true); }} className="msg-form">
          <textarea value={message} onChange={event => setMessage(event.target.value)}
            onKeyDown={event => { if (event.ctrlKey && event.key === "Enter") { event.preventDefault(); startTurn(message, true); } }}
            disabled={busy} placeholder="描述你想获得的科研结果…" rows={2} />
          <div className="msg-actions">
            <button disabled={!runId || !message.trim() || busy} className="send-btn">Send</button>
            <button type="button" className="cancel-btn" onClick={() => control("cancel")} disabled={!BUSY.has(turnState)}>Cancel</button>
            <button type="button" className={`pause-btn ${turnState === "running" ? "pause-on" : ""}`} onClick={() => control("pause")} disabled={turnState !== "running"}>
              {turnState === "pause_requested" ? "Pausing…" : "Pause"}
            </button>
            <button type="button" className={`resume-btn ${["paused", "rate_limited"].includes(turnState) ? "resume-on" : ""}`} onClick={() => control("resume")} disabled={!(["paused", "rate_limited"].includes(turnState))}>Resume</button>
            <button type="button" className={`plan-btn ${planActive ? "plan-active" : ""}`} onClick={() => startTurn("/plan", false)} disabled={busy}>{planActive ? "Plan ON" : "Plan"}</button>
            <button type="button" className={`approve-btn ${pendingApproval ? "approve-on" : ""}`} onClick={() => resolveApproval(true)} disabled={!pendingApproval || turnState !== "waiting_approval"}>Accept</button>
            <button type="button" className={`reject-btn ${pendingApproval ? "reject-on" : ""}`} onClick={() => resolveApproval(false)} disabled={!pendingApproval || turnState !== "waiting_approval"}>Reject</button>
          </div>
        </form>
        {activeTurnId && <div className="turn-id">Turn {activeTurnId.slice(0, 8)}</div>}
      </section>
      </div>
      {setupOpen && <div className="modal-overlay" onClick={() => setSetupOpen(false)}>
        <div className="modal-box" onClick={e => e.stopPropagation()}>
          <h2>Quick Setup</h2>
          <label>Provider
            <select value={setupProvider} onChange={e => {
              setSetupProvider(e.target.value);
              const p = setupPresets.find(x => x.name === e.target.value);
              if (p) { setSetupUrl(p.base_url); setSetupModel(p.model); setSetupCtx(String(p.context || 0)); }
            }}>
              <option value="">Select...</option>
              {setupPresets.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
          </label>
          <label>API Key <input value={setupKey} onChange={e => setSetupKey(e.target.value)} type="password" /></label>
          <label>Base URL <input value={setupUrl} onChange={e => setSetupUrl(e.target.value)} /></label>
          <label>Model <input value={setupModel} onChange={e => setSetupModel(e.target.value)} /></label>
          <div className="modal-adv-toggle" onClick={() => setSetupAdvanced(!setupAdvanced)}>Advanced {setupAdvanced ? "[-]" : "[+]"}</div>
          {setupAdvanced && <>
            <label>Context Window (K) <input value={Math.round(parseInt(setupCtx||"0")/1000)} onChange={e => setSetupCtx(String(parseInt(e.target.value||"0")*1000))} /> <small>Limits total tokens per conversation to prevent cost runaway.</small></label>
            <label>Timeout (seconds) <input value={setupTimeout} onChange={e => setSetupTimeout(e.target.value)} /> <small>Maximum wait time for each model response before retrying.</small></label>
            <label>Max Concurrency <input value={setupConcurrency} onChange={e => setSetupConcurrency(e.target.value)} type="number" min="1" max="10" /> <small>How many simultaneous model requests are allowed. Higher = faster but may hit rate limits.</small></label>
          </>}
          <div className="modal-actions">
            <button onClick={async () => {
              await fetch(`${API}/setup/apply`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({
                llm_provider: setupProvider.toLowerCase().split(" ")[0],
                llm_model: setupModel,
                llm_base_url: setupUrl,
                llm_api_key: setupKey,
                context_window: setupCtx,
                llm_timeout: setupTimeout,
                max_concurrency: setupConcurrency,
              }) });
              setSetupOpen(false);
              alert(".env updated. Restart backend to apply.");
            }}>Apply</button>
            <button onClick={() => setSetupOpen(false)}>Cancel</button>
          </div>
        </div>
      </div>}
    </div>
  );
}
