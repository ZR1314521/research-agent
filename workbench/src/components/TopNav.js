import { useEffect, useRef, useState } from "react";
import { THEME_CHANGE_EVENT } from "../theme";

const NAV_ITEMS = [
  { key: "home", label: "首页" },
  { key: "workspace", label: "科研工作台" },
  { key: "tasks", label: "任务中心" },
  { key: "settings", label: "设置" },
];

const SCROLL_BEHAVIOR = Object.freeze({ alwaysVisibleUntil: 32, directionThreshold: 6 });

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
  const [hidden, setHidden] = useState(false);
  const lastScroll = useRef(typeof window === "undefined" ? 0 : window.scrollY);

  useEffect(() => {
    const autoHideEnabled = () => document.documentElement.dataset.navAutoHide !== "false";
    const onScroll = () => {
      const next = Math.max(0, window.scrollY || 0);
      const delta = next - lastScroll.current;
      if (!autoHideEnabled() || next <= SCROLL_BEHAVIOR.alwaysVisibleUntil) setHidden(false);
      else if (Math.abs(delta) >= SCROLL_BEHAVIOR.directionThreshold) setHidden(delta > 0);
      lastScroll.current = next;
    };
    const onThemeChange = event => {
      if (event.detail?.navigation?.autoHide === false) setHidden(false);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener(THEME_CHANGE_EVENT, onThemeChange);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener(THEME_CHANGE_EVENT, onThemeChange);
    };
  }, []);
  return (
    <header className={`top-nav ${hidden ? "is-hidden" : ""}`}>
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
