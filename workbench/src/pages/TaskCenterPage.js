import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "../components/Icon";

const FILTERS = [
  { key: "all", label: "全部" }, { key: "running", label: "运行中" },
  { key: "idle", label: "就绪" },
  { key: "waiting", label: "待确认" }, { key: "paused", label: "已暂停" },
  { key: "failed", label: "失败" }, { key: "completed", label: "已完成" },
];

export function statusInfo(raw) {
  const status = String(raw || "").toLowerCase();
  if (["running", "pause_requested", "rate_limited"].includes(status)) return { key: "running", label: "运行中", progress: null, detail: "步骤数量由任务动态决定" };
  if (["active", "idle", "planning", "waiting_user"].includes(status)) return { key: "idle", label: status === "waiting_user" ? "待继续" : "就绪", progress: null, detail: "当前没有后台执行" };
  if (["waiting_approval", "needs_user"].includes(status)) return { key: "waiting", label: "待确认", progress: null, detail: "等待人工决定" };
  if (status === "paused") return { key: "paused", label: "已暂停", progress: null, detail: "可调整后继续" };
  if (["failed", "error", "cancelled"].includes(status)) return { key: "failed", label: status === "cancelled" ? "已取消" : "失败", progress: null, detail: "已完成产物仍保留" };
  if (status === "completed") return { key: "completed", label: "已完成", progress: 100, detail: "任务已完成" };
  return { key: "idle", label: "就绪", progress: null, detail: "当前没有后台执行" };
}

function dateLabel(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace("T", " ");
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || response.statusText);
  return body;
}

function nextHourValue() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(0, 0, 0);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function ScheduleForm({ api, onSaved, onClose }) {
  const [form, setForm] = useState({ name: "", prompt: "", schedule_type: "once", next_run_at: nextHourValue(), timezone: "Asia/Shanghai" });
  const [error, setError] = useState("");
  const save = async event => {
    event.preventDefault(); setError("");
    try {
      await apiJson(`${api}/schedules`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      onSaved(); onClose();
    } catch (eventError) { setError(eventError.message); }
  };
  return <form className="schedule-form" onSubmit={save}><header><div><span>新建定时任务</span><h2>让 Agent 到点自动开始工作</h2><p>浏览器可以关闭，但本地后端需要保持运行。</p></div><button type="button" onClick={onClose}><Icon name="x" size={18} /></button></header><div className="schedule-form-grid"><label>任务名称<input required value={form.name} onChange={event => setForm(value => ({ ...value, name: event.target.value }))} placeholder="例如：每日脑电文献简报" /></label><label>执行频率<select value={form.schedule_type} onChange={event => setForm(value => ({ ...value, schedule_type: event.target.value }))}><option value="once">仅一次</option><option value="daily">每天</option><option value="weekly">每周</option></select></label><label>下一次执行时间<input required type="datetime-local" value={form.next_run_at} onChange={event => setForm(value => ({ ...value, next_run_at: event.target.value }))} /></label><label>时区<input value="Asia/Shanghai（UTC+8）" disabled /></label><label className="schedule-prompt">完整 Agent 指令<textarea required rows="5" value={form.prompt} onChange={event => setForm(value => ({ ...value, prompt: event.target.value }))} placeholder="例如：检索过去 24 小时新增的抑郁症脑电研究，筛选最相关的 10 篇，生成中文摘要和文献矩阵。" /></label></div>{error && <div className="settings-alert error">{error}</div>}<footer><span>如果任务请求敏感操作，将进入“待确认”并等待你允许或拒绝。</span><div><button type="button" className="secondary-action" onClick={onClose}>取消</button><button className="primary-action">创建任务</button></div></footer></form>;
}

function ScheduledTasks({ api, onOpen }) {
  const [items, setItems] = useState([]);
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [deleteId, setDeleteId] = useState("");
  const load = useCallback(() => Promise.all([apiJson(`${api}/schedules`), apiJson(`${api}/schedule-runs?limit=30`)]).then(([schedules, executions]) => { setItems(schedules); setRuns(executions); }).catch(event => setError(event.message)), [api]);
  useEffect(() => { load(); const timer = window.setInterval(load, 5000); return () => window.clearInterval(timer); }, [load]);
  const post = async (url, body) => { await apiJson(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); await load(); };
  const toggle = item => post(`${api}/schedules/${item.id}`, { enabled: !item.enabled }).catch(event => setError(event.message));
  const run = item => post(`${api}/schedules/${item.id}/run`).catch(event => setError(event.message));
  const remove = item => post(`${api}/schedules/${item.id}/delete`).then(() => setDeleteId("")).catch(event => setError(event.message));
  return (
    <div className="scheduled-layout">
      <section className="schedule-list-panel">
        {error && <div className="settings-alert error">{error}</div>}
        {items.map(item => (
          <article className={`schedule-row ${item.enabled ? "" : "paused"}`} key={item.id}>
            <span className="schedule-icon"><Icon name="clock" size={18} /></span>
            <div className="schedule-main">
              <header>
                <h3>{item.name}</h3>
                <span className={`schedule-status ${item.status}`}>
                  {item.status === "waiting_approval" ? "待确认" : item.status === "scheduled" ? "已安排" : item.status === "running" ? "运行中" : item.status === "missed" ? "已错过" : item.status === "paused" ? "已暂停" : item.status}
                </span>
              </header>
              <p>{item.prompt}</p>
              <div>
                <span>{item.schedule_type === "once" ? "仅一次" : item.schedule_type === "daily" ? "每天" : "每周"}</span>
                <span>下次：{dateLabel(item.next_run_at)}</span>
                {item.last_run_at && <span>上次：{dateLabel(item.last_run_at)}</span>}
              </div>
              {item.last_error && <small className="schedule-error">{item.last_error}</small>}
            </div>
            <div className="schedule-actions">
              <button onClick={() => run(item)}>立即运行</button>
              {item.next_run_at && <button onClick={() => toggle(item)}>{item.enabled ? "暂停计划" : "恢复计划"}</button>}
              {item.last_run_id && <button onClick={() => onOpen(item.last_run_id)}>打开会话</button>}
              {deleteId === item.id ? (
                <span className="inline-confirm">
                  <button className="danger-text" onClick={() => remove(item)}>确认删除</button>
                  <button onClick={() => setDeleteId("")}>取消</button>
                </span>
              ) : <button className="danger-text" onClick={() => setDeleteId(item.id)}>删除</button>}
            </div>
          </article>
        ))}
        {!items.length && (
          <div className="scheduled-empty compact-empty">
            <span className="empty-illustration"><Icon name="clock" size={32} /></span>
            <h2>还没有定时任务</h2>
            <p>创建任务后，后端会在指定时间自动创建新会话并交给 Agent 执行。</p>
          </div>
        )}
      </section>
      <aside className="schedule-runs">
        <h2>最近执行</h2>
        {runs.slice(0, 12).map(item => (
          <button key={item.id} onClick={() => item.run_id && onOpen(item.run_id)} disabled={!item.run_id}>
            <span className={`execution-dot ${item.status}`} />
            <p>
              <strong>{items.find(schedule => schedule.id === item.schedule_id)?.name || "已删除的计划"}</strong>
              <small>{item.status === "waiting_approval" ? "等待人工确认" : item.status} · {dateLabel(item.started_at)}</small>
            </p>
            <Icon name="chevronRight" size={16} />
          </button>
        ))}
        {!runs.length && <p className="no-executions">暂无执行记录</p>}
      </aside>
    </div>
  );
}

export default function TaskCenterPage({ api, sessions, onOpen, onRefresh }) {
  const [tab, setTab] = useState("all");
  const [filter, setFilter] = useState("all");
  const [formOpen, setFormOpen] = useState(false);
  const [scheduleRevision, setScheduleRevision] = useState(0);
  const rows = useMemo(() => sessions.map(session => ({ ...session, info: statusInfo(session.status) })), [sessions]);
  const visible = filter === "all" ? rows : rows.filter(row => row.info.key === filter);
  const counts = useMemo(() => ({
    running: rows.filter(row => row.info.key === "running").length,
    idle: rows.filter(row => row.info.key === "idle").length,
    waiting: rows.filter(row => row.info.key === "waiting").length,
    completed: rows.filter(row => row.info.key === "completed").length,
  }), [rows]);
  return (
    <main className="task-page page-frame">
      <div className="page-title-row"><div className="page-title"><span className="title-icon"><Icon name="checkSquare" size={24} /></span><div><h1>任务中心</h1><p>状态来自真实后台执行，不估算虚假百分比</p></div></div><button className="primary-action" onClick={() => { setTab("scheduled"); setFormOpen(true); }}><Icon name="plus" className="btn-icon" />新建定时任务</button></div>
      {formOpen && <ScheduleForm api={api} onSaved={() => setScheduleRevision(value => value + 1)} onClose={() => setFormOpen(false)} />}
      <div className="task-tabs"><button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>全部任务</button><button className={tab === "scheduled" ? "active" : ""} onClick={() => setTab("scheduled")}>定时任务</button></div>
      {tab === "scheduled" ? <ScheduledTasks api={api} onOpen={onOpen} key={scheduleRevision} /> : (
        <div className="task-layout"><section className="task-list-panel">
          <div className="task-filters">{FILTERS.map(item => <button key={item.key} className={filter === item.key ? "active" : ""} onClick={() => setFilter(item.key)}>{item.label}</button>)}<button className="refresh-tasks" onClick={onRefresh}>刷新</button></div>
          <div className="task-table-head"><span>任务</span><span>状态</span><span>当前进度</span><span>更新时间</span><span>结果</span><span>操作</span></div>
          <div className="task-rows">{visible.map(row => <article className="task-row" key={row.run_id}><div className="task-name"><span className="task-type-icon"><Icon name="document" size={16} /></span><strong>{row.title || "未命名科研任务"}</strong></div><span className={`task-status status-${row.info.key}`}><i />{row.info.label}</span><div className={`task-progress status-${row.info.key} ${row.info.progress == null ? "indeterminate" : ""}`}><span>{row.info.detail}</span><div>{row.info.progress == null ? <i /> : <i style={{ width: `${row.info.progress}%` }} />}</div></div><time>{dateLabel(row.updated_at || row.created_at)}</time><span className="task-result">—</span><button className="row-action" onClick={() => onOpen(row.run_id)}>打开</button></article>)}{!visible.length && <div className="empty-row"><Icon name="activity" size={24} /><p>当前没有符合条件的任务</p></div>}</div>
          <footer className="task-table-footer">共 {visible.length} 条任务</footer>
        </section><aside className="task-summary"><section><h2>任务状态</h2><p><span className="summary-dot running"><Icon name="play" size={12} /></span>运行中<strong>{counts.running}</strong></p><p><span className="summary-dot"><Icon name="dot" size={10} /></span>就绪<strong>{counts.idle}</strong></p><p><span className="summary-dot waiting"><Icon name="clock" size={12} /></span>待确认<strong>{counts.waiting}</strong></p><p><span className="summary-dot done"><Icon name="check" size={12} /></span>已完成<strong>{counts.completed}</strong></p></section><section><h2>定时执行</h2><div className="no-schedule"><Icon name="clock" size={24} /><p>后端运行时持续调度<br /><small>浏览器可以安全关闭</small></p></div></section></aside></div>
      )}
    </main>
  );
}
