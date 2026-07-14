const NAV_ITEMS = [
  { key: "home", label: "首页" },
  { key: "workspace", label: "科研工作台" },
  { key: "tasks", label: "任务中心" },
  { key: "settings", label: "设置" },
];

export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <i className="brand-node node-a" />
      <i className="brand-node node-b" />
      <i className="brand-node node-c" />
      <i className="brand-link link-a" />
      <i className="brand-link link-b" />
    </span>
  );
}

export default function TopNav({ page, onNavigate, account }) {
  const initials = String(account?.display_name || "研").trim().slice(0, 2) || "研";
  return (
    <header className="top-nav">
      <button className="brand-button" onClick={() => onNavigate("home")} aria-label="返回首页">
        <BrandMark />
        <span>Research Agent</span>
      </button>
      <nav className="main-nav" aria-label="主导航">
        {NAV_ITEMS.map(item => (
          <button
            key={item.key}
            className={`nav-item ${page === item.key ? "active" : ""}`}
            onClick={() => onNavigate(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <span className="user-avatar profile-avatar" aria-label={account?.display_name || "本地用户"} title={account?.display_name || "本地用户"}>{initials}</span>
    </header>
  );
}
