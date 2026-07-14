export default function ApprovalDock({ pending, onResolve }) {
  if (!pending) return null;
  const summary = pending.summary || pending.message || "确认后 Agent 才会继续执行。";
  const operation = pending.skill || (pending.type === "plan_approval" ? "执行当前计划" : "敏感操作");

  return (
    <section className="approval-dock" role="alert" aria-live="assertive">
      <span className="approval-icon">!</span>
      <div>
        <small>等待你的决定 · {operation}</small>
        <strong>这一步需要授权</strong>
        <p>{summary}</p>
      </div>
      <div className="approval-dock-actions">
        <button type="button" className="reject-action" onClick={() => onResolve(false)}>拒绝</button>
        <button type="button" className="approve-action" onClick={() => onResolve(true)}>允许并继续</button>
      </div>
    </section>
  );
}
