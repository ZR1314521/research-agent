import { useMemo, useState } from "react";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "running", label: "运行中" },
  { key: "waiting", label: "待确认" },
  { key: "paused", label: "已暂停" },
  { key: "failed", label: "失败" },
  { key: "completed", label: "已完成" },
];

function statusInfo(raw) {
  const status = String(raw || "").toLowerCase();
  if (["active", "running", "pause_requested", "rate_limited"].includes(status)) return { key: "running", label: "运行中", progress: 45 };
  if (["waiting_user", "waiting_approval", "needs_user"].includes(status)) return { key: "waiting", label: "待确认", progress: 82 };
  if (status === "paused") return { key: "paused", label: "已暂停", progress: 35 };
  if (["failed", "error", "cancelled"].includes(status)) return { key: "failed", label: status === "cancelled" ? "已取消" : "失败", progress: 18 };
  if (status === "completed") return { key: "completed", label: "已完成", progress: 100 };
  return { key: "paused", label: "未开始", progress: 0 };
}

function dateLabel(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16).replace("T", " ");
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function TaskCenterPage({ sessions, onOpen, onRefresh }) {
  const [tab, setTab] = useState("all");
  const [filter, setFilter] = useState("all");
  const [notice, setNotice] = useState("");
  const rows = useMemo(() => sessions.map(session => ({ ...session, info: statusInfo(session.status) })), [sessions]);
  const visible = filter === "all" ? rows : rows.filter(row => row.info.key === filter);
  const counts = useMemo(() => ({
    running: rows.filter(row => row.info.key === "running").length,
    waiting: rows.filter(row => row.info.key === "waiting").length,
    completed: rows.filter(row => row.info.key === "completed").length,
  }), [rows]);

  return (
    <main className="task-page page-frame">
      <div className="page-title-row">
        <div className="page-title"><span className="title-icon">▣</span><div><h1>任务中心</h1><p>查看、管理与安排 Agent 任务</p></div></div>
        <button className="primary-action" onClick={() => setNotice("定时任务功能将在下一阶段开放。")}>＋ 新建定时任务</button>
      </div>
      {notice && <div className="inline-notice">{notice}<button onClick={() => setNotice("")}>×</button></div>}
      <div className="task-tabs">
        <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>全部任务</button>
        <button className={tab === "scheduled" ? "active" : ""} onClick={() => setTab("scheduled")}>定时任务</button>
      </div>

      {tab === "scheduled" ? (
        <section className="scheduled-empty">
          <span className="empty-illustration">◷</span>
          <h2>定时任务将在下一阶段开放</h2>
          <p>届时可预约一次或周期执行科研任务，并设置错过任务后的处理方式。</p>
        </section>
      ) : (
        <div className="task-layout">
          <section className="task-list-panel">
            <div className="task-filters">
              {FILTERS.map(item => <button key={item.key} className={filter === item.key ? "active" : ""} onClick={() => setFilter(item.key)}>{item.label}</button>)}
              <button className="refresh-tasks" onClick={onRefresh}>刷新</button>
            </div>
            <div className="task-table-head"><span>任务</span><span>状态</span><span>当前进度</span><span>更新时间</span><span>结果</span><span>操作</span></div>
            <div className="task-rows">
              {visible.map(row => (
                <article className="task-row" key={row.run_id}>
                  <div className="task-name"><span className="task-type-icon">▤</span><strong>{row.title || "未命名科研任务"}</strong></div>
                  <span className={`task-status status-${row.info.key}`}><i />{row.info.label}</span>
                  <div className="task-progress"><span>{row.info.key === "completed" ? "已完成全部步骤" : row.info.key === "waiting" ? "等待人工确认" : "Agent 工作流"}</span><div><i style={{ width: `${row.info.progress}%` }} /></div></div>
                  <time>{dateLabel(row.updated_at || row.created_at)}</time>
                  <span className="task-result">—</span>
                  <button className="row-action" onClick={() => onOpen(row.run_id)}>打开</button>
                </article>
              ))}
              {!visible.length && <div className="empty-row"><span>⌁</span><p>当前没有符合条件的任务</p></div>}
            </div>
            <footer className="task-table-footer">共 {visible.length} 条任务</footer>
          </section>
          <aside className="task-summary">
            <section><h2>今日任务</h2><p><span className="summary-dot running">▶</span>运行中<strong>{counts.running}</strong></p><p><span className="summary-dot waiting">◷</span>待确认<strong>{counts.waiting}</strong></p><p><span className="summary-dot done">✓</span>已完成<strong>{counts.completed}</strong></p></section>
            <section><h2>下一次定时任务</h2><div className="no-schedule"><span>◷</span><p>尚未设置<br /><small>定时能力后续开放</small></p></div></section>
          </aside>
        </div>
      )}
    </main>
  );
}
