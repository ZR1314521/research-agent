import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  COLOR_FIELDS,
  DEFAULT_THEME,
  FONT_OPTIONS,
  THEME_PRESETS,
  THEME_TYPES,
  applyTheme,
  loadTheme,
  parseThemeImport,
  saveTheme,
} from "../theme";
import Icon from "../components/Icon";

const SECTIONS = [
  ["quick", "settings", "快速设置"],
  ["usage", "activity", "用量统计"],
  ["sources", "document", "学术数据源"],
  ["theme", "palette", "色彩设计"],
  ["privacy", "shield", "权限与隐私"],
  ["account", "checkSquare", "账号信息"],
];

const PROVIDER_LINKS = {
  deepseek: { site: "https://www.deepseek.com/", key: "https://platform.deepseek.com/api_keys", docs: "https://api-docs.deepseek.com/" },
  openai: { site: "https://openai.com/", key: "https://platform.openai.com/api-keys", docs: "https://platform.openai.com/docs/" },
  qwen: { site: "https://www.alibabacloud.com/product/model-studio", key: "https://bailian.console.aliyun.com/", docs: "https://help.aliyun.com/zh/model-studio/" },
  moonshot: { site: "https://www.moonshot.cn/", key: "https://platform.moonshot.cn/console/api-keys", docs: "https://platform.moonshot.cn/docs/" },
  zhipu: { site: "https://www.bigmodel.cn/", key: "https://open.bigmodel.cn/usercenter/apikeys", docs: "https://docs.bigmodel.cn/" },
};

function providerKey(value) {
  const name = String(value || "").toLowerCase();
  if (name.includes("deepseek")) return "deepseek";
  if (name.includes("openai")) return "openai";
  if (name.includes("qwen") || name.includes("通义")) return "qwen";
  if (name.includes("moonshot") || name.includes("kimi")) return "moonshot";
  if (name.includes("zhipu") || name.includes("智谱")) return "zhipu";
  return "";
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || response.statusText);
  return body;
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function SectionHeading({ title, text, actions }) {
  return <div className="settings-heading settings-heading-row"><div><h1>{title}</h1><p>{text}</p></div>{actions}</div>;
}

function QuickSetup({ api }) {
  const [presets, setPresets] = useState([]);
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [context, setContext] = useState("");
  const [timeout, setTimeoutValue] = useState("300");
  const [concurrency, setConcurrency] = useState("1");
  const [advanced, setAdvanced] = useState(false);
  const [status, setStatus] = useState({ kind: "", text: "" });

  useEffect(() => {
    Promise.all([apiJson(`${api}/setup/presets`), apiJson(`${api}/health`)]).then(([items, health]) => {
      setPresets(items);
      const match = items.find(item => providerKey(item.name) === providerKey(health.provider));
      if (match) {
        setProvider(match.name); setBaseUrl(match.base_url || ""); setModel(health.model || match.model || ""); setContext(String(health.context_window || match.context || ""));
      } else if (health.provider || health.model) {
        setProvider(health.provider || "自定义"); setModel(health.model || "");
      }
    }).catch(error => setStatus({ kind: "error", text: `暂时无法读取当前配置：${error.message}` }));
  }, [api]);

  const links = useMemo(() => PROVIDER_LINKS[providerKey(provider)] || null, [provider]);
  const chooseProvider = value => {
    setProvider(value);
    const item = presets.find(preset => preset.name === value);
    if (item) { setBaseUrl(item.base_url || ""); setModel(item.model || ""); setContext(String(item.context || "")); }
    setStatus({ kind: "", text: "" });
  };
  const testConnection = async () => {
    setStatus({ kind: "checking", text: "正在检查本地后端…" });
    try { await apiJson(`${api}/health`); setStatus({ kind: "success", text: "后端连接正常；保存新模型配置后需要重启" }); }
    catch (error) { setStatus({ kind: "error", text: `连接失败：${error.message}` }); }
  };
  const save = async () => {
    if (!provider || !baseUrl || !model) { setStatus({ kind: "error", text: "请完整填写服务商、Base URL 和模型名称" }); return; }
    setStatus({ kind: "checking", text: "正在保存…" });
    try {
      await apiJson(`${api}/setup/apply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ llm_provider: providerKey(provider) || provider.toLowerCase().split(" ")[0], llm_model: model, llm_base_url: baseUrl, llm_api_key: apiKey, context_window: context, llm_timeout: timeout, max_concurrency: concurrency }) });
      setApiKey(""); setStatus({ kind: "success", text: "配置已保存，请重启后端使其生效" });
    } catch (error) { setStatus({ kind: "error", text: `保存失败：${error.message}` }); }
  };

  return <>
    <SectionHeading title="快速设置" text="连接你的模型服务，即可开始使用" />
    <section className="quick-setup-card">
      <div className="form-row provider-row"><label htmlFor="provider">模型服务提供商</label><div className="field-stack"><select id="provider" value={provider} onChange={event => chooseProvider(event.target.value)}><option value="">选择服务商</option>{presets.map(item => <option value={item.name} key={item.name}>{item.name}</option>)}<option value="自定义">自定义 OpenAI 兼容服务</option></select>{links && <div className="provider-links"><a href={links.site} target="_blank" rel="noreferrer">官方网站 <Icon name="externalLink" size={12} /></a><a href={links.key} target="_blank" rel="noreferrer">申请 API Key <Icon name="externalLink" size={12} /></a><a href={links.docs} target="_blank" rel="noreferrer">官方文档 <Icon name="externalLink" size={12} /></a></div>}</div></div>
      <div className="form-row"><label htmlFor="api-key">API Key</label><div className="password-field"><input id="api-key" type={showKey ? "text" : "password"} value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder="输入后仅保存到本机配置" /><button onClick={() => setShowKey(value => !value)} type="button">{showKey ? "隐藏" : "显示"}</button></div></div>
      <div className="form-row"><label htmlFor="base-url">Base URL</label><input id="base-url" value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" /></div>
      <div className="form-row"><label htmlFor="model-name">模型名称</label><input id="model-name" value={model} onChange={event => setModel(event.target.value)} placeholder="输入模型标识" /></div>
      <button className="advanced-toggle" onClick={() => setAdvanced(value => !value)}><span>高级选项</span><Icon name={advanced ? "chevronUp" : "chevronDown"} size={16} /></button>
      {advanced && <div className="advanced-grid"><label>上下文长度<input type="number" min="0" value={context} onChange={event => setContext(event.target.value)} /></label><label>请求超时（秒）<input type="number" min="5" value={timeout} onChange={event => setTimeoutValue(event.target.value)} /></label><label>最大并发数<input type="number" min="1" max="10" value={concurrency} onChange={event => setConcurrency(event.target.value)} /></label></div>}
      <footer className="setup-actions"><span className={`connection-status ${status.kind}`}><i />{status.text || "填写配置后可以检查连接"}</span><div><button className="secondary-action" onClick={testConnection}>测试连接</button><button className="primary-action" onClick={save}>保存并应用</button></div></footer>
    </section>
  </>;
}

function UsageTrend({ items }) {
  if (!items.length) return <div className="chart-empty"><Icon name="activity" size={28} /><p>完成任务后，这里会显示真实趋势</p></div>;
  const width = 920, height = 260, pad = 26;
  const values = items.map(item => Number(item.input || 0) + Number(item.output || 0));
  const max = Math.max(...values, 1);
  const pointList = values.map((value, index) => {
    const x = pad + index * ((width - pad * 2) / Math.max(1, values.length - 1));
    const y = height - pad - value / max * (height - pad * 2);
    return [x, y];
  });
  const points = pointList.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `M ${pad} ${height - pad} L ${pointList.map(([x, y]) => `${x} ${y}`).join(" L ")} L ${width - pad} ${height - pad} Z`;
  return <div className="usage-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Token 使用趋势"><defs><linearGradient id="usage-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--sage-4)" stopOpacity=".28"/><stop offset="1" stopColor="var(--sage-4)" stopOpacity="0"/></linearGradient></defs><path d={area} fill="url(#usage-fill)"/><polyline points={points} fill="none" stroke="var(--sage-4)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>{points.split(" ").map((point, index) => { const [cx, cy] = point.split(","); return <circle key={items[index]?.time || index} cx={cx} cy={cy} r="4" fill="var(--cream-0)" stroke="var(--sage-4)" strokeWidth="3"/>; })}</svg><div className="chart-labels"><span>{items[0]?.time?.slice(5) || ""}</span><span>{items[items.length - 1]?.time?.slice(5) || ""}</span></div></div>;
}

function UsagePanel({ api }) {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("records");
  const [filters, setFilters] = useState({ provider: "", model: "", status: "" });
  const [error, setError] = useState("");
  const load = useCallback(() => {
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
    apiJson(`${api}/usage?${query}`).then(setData).catch(event => setError(event.message));
  }, [api, filters]);
  useEffect(() => { load(); }, [load]);
  const summary = data?.summary || {};
  const rows = tab === "providers" ? data?.providers || [] : tab === "models" ? data?.models || [] : data?.records || [];
  return <>
    <SectionHeading title="用量统计" text="所有数字都来自本机 Provider 调用日志" actions={<button className="secondary-action compact-action" onClick={load}>刷新</button>} />
    {error && <div className="settings-alert error">{error}</div>}
    <div className="usage-filter-row"><select value={filters.provider} onChange={event => setFilters(value => ({ ...value, provider: event.target.value }))}><option value="">全部来源</option>{(data?.filters?.providers || []).map(value => <option key={value}>{value}</option>)}</select><select value={filters.model} onChange={event => setFilters(value => ({ ...value, model: event.target.value }))}><option value="">全部模型</option>{(data?.filters?.models || []).map(value => <option key={value}>{value}</option>)}</select><select value={filters.status} onChange={event => setFilters(value => ({ ...value, status: event.target.value }))}><option value="">全部状态</option>{(data?.filters?.statuses || []).map(value => <option key={value}>{value}</option>)}</select></div>
    <section className="usage-overview">
      <div className="usage-primary"><span className="metric-symbol"><Icon name="zap" size={28} /></span><div><small>真实消耗 Tokens</small><strong>{formatNumber(summary.total_tokens)}</strong><span>{formatNumber(summary.requests)} 次请求</span></div></div>
      <div className="usage-cost">
        <small>总费用</small>
        <strong>{summary.cost === null || summary.cost === undefined ? "费用暂未估算" : `$${summary.cost}`}</strong>
        {(summary.cost === null || summary.cost === undefined) && <span>未配置模型单价，Token 统计不受影响</span>}
      </div>
      <div className="usage-mini-grid"><article><small>输入</small><strong>{formatNumber(summary.input_tokens)}</strong></article><article><small>输出</small><strong>{formatNumber(summary.output_tokens)}</strong></article><article><small>缓存命中</small><strong>{formatNumber(summary.cached_tokens)}</strong></article><article><small>成功率</small><strong>{formatNumber(summary.success_rate)}%</strong></article></div>
    </section>
    <section className="usage-trend-card"><header><div><h2>使用趋势</h2><p>输入与输出 Token 的确定性汇总</p></div><span>{summary.damaged_records ? `${summary.damaged_records} 条损坏记录已跳过` : "日志完整"}</span></header><UsageTrend items={data?.trend || []} /></section>
    <section className="usage-detail-card"><div className="usage-tabs"><button className={tab === "records" ? "active" : ""} onClick={() => setTab("records")}>请求日志</button><button className={tab === "providers" ? "active" : ""} onClick={() => setTab("providers")}>Provider 统计</button><button className={tab === "models" ? "active" : ""} onClick={() => setTab("models")}>模型统计</button></div>{tab === "records" ? <div className="usage-table"><div className="usage-table-head"><span>时间</span><span>提供商 / 模型</span><span>输入</span><span>输出</span><span>耗时</span><span>费用</span><span>状态</span></div>{rows.map(item => <div className="usage-table-row" key={item.call_id || `${item.run_id}-${item.time}`}><time>{formatDate(item.time)}</time><span><strong>{item.provider}</strong><small>{item.model}</small></span><span>{formatNumber(item.input_tokens)}</span><span>{formatNumber(item.output_tokens)}</span><span>{(item.duration_ms / 1000).toFixed(1)}s</span><span title={item.priced ? "" : "未配置该模型单价"}>{item.priced ? `$${item.cost}` : "未估算"}</span><span className={`usage-status ${item.status}`}>{item.status}</span></div>)}{!rows.length && <div className="usage-empty-row">暂无调用记录</div>}</div> : <div className="aggregate-grid">{rows.map(item => <article key={item.name}><span>{item.name}</span><strong>{formatNumber(item.tokens)} Tokens</strong><small>{item.requests} 次请求 · {(item.duration_ms / 1000).toFixed(1)} 秒</small></article>)}{!rows.length && <div className="usage-empty-row">暂无统计</div>}</div>}</section>
  </>;
}

function DataSourcesPanel({ api }) {
  const [sources, setSources] = useState([]);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ kind: "free", name: "", base_url: "", username: "", password: "" });
  const [status, setStatus] = useState({ kind: "", text: "" });
  const [deleteId, setDeleteId] = useState("");
  const load = useCallback(() => apiJson(`${api}/data-sources`).then(setSources).catch(error => setStatus({ kind: "error", text: error.message })), [api]);
  useEffect(() => { load(); }, [load]);
  const mutate = async (url, body) => { await apiJson(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }); await load(); };
  const save = async event => {
    event.preventDefault(); setStatus({ kind: "checking", text: "正在保存数据源…" });
    try { await mutate(`${api}/data-sources`, form); setForm({ kind: "free", name: "", base_url: "", username: "", password: "" }); setFormOpen(false); setStatus({ kind: "success", text: "数据源已保存在本机" }); }
    catch (error) { setStatus({ kind: "error", text: error.message }); }
  };
  const toggle = async source => { try { await mutate(`${api}/data-sources/${source.id}`, { enabled: !source.enabled }); } catch (error) { setStatus({ kind: "error", text: error.message }); } };
  const check = async source => { setStatus({ kind: "checking", text: `正在检测 ${source.name}…` }); try { const value = await apiJson(`${api}/data-sources/${source.id}/check`, { method: "POST" }); await load(); setStatus({ kind: value.status === "available" ? "success" : "error", text: value.status_message }); } catch (error) { setStatus({ kind: "error", text: error.message }); } };
  const remove = async id => { try { await mutate(`${api}/data-sources/${id}/delete`); setDeleteId(""); setStatus({ kind: "success", text: "数据源和本机凭据已删除" }); } catch (error) { setStatus({ kind: "error", text: error.message }); } };
  return <>
    <SectionHeading title="学术数据源" text="管理 Agent 可以访问的公开来源和本机付费来源" actions={<button className="primary-action compact-action" onClick={() => setFormOpen(value => !value)}><Icon name="plus" className="btn-icon" />新增数据源</button>} />
    {status.text && <div className={`settings-alert ${status.kind}`}>{status.text}</div>}
    {formOpen && <form className="source-form" onSubmit={save}><header><div><h2>新增数据源</h2><p>免费来源用于限定域名检索；付费凭据只在本机加密保存</p></div><button type="button" onClick={() => setFormOpen(false)}><Icon name="x" size={18} /></button></header><div className="source-kind-switch"><button type="button" className={form.kind === "free" ? "active" : ""} onClick={() => setForm(value => ({ ...value, kind: "free" }))}>免费来源</button><button type="button" className={form.kind === "paid" ? "active" : ""} onClick={() => setForm(value => ({ ...value, kind: "paid" }))}>付费来源</button></div><label>数据源名称<input required value={form.name} onChange={event => setForm(value => ({ ...value, name: event.target.value }))} placeholder="例如：实验室论文库" /></label><label>网站或接口地址<input required type="url" value={form.base_url} onChange={event => setForm(value => ({ ...value, base_url: event.target.value }))} placeholder="https://example.org" /></label>{form.kind === "paid" && <div className="paid-fields"><label>账号<input required value={form.username} onChange={event => setForm(value => ({ ...value, username: event.target.value }))} autoComplete="off" /></label><label>密码<input required type="password" value={form.password} onChange={event => setForm(value => ({ ...value, password: event.target.value }))} autoComplete="new-password" /></label></div>}<footer><span>{form.kind === "paid" ? "使用当前 Windows 用户加密，暂不自动登录外部网站" : "保存后 Agent 可在网页检索中限定该域名"}</span><button className="primary-action">保存数据源</button></footer></form>}
    <div className="source-list">{sources.map(source => <article className={`source-card ${source.enabled ? "" : "disabled"}`} key={source.id}><div className="source-brand"><span>{source.name.slice(0, 2)}</span><div><h3>{source.name}</h3><p>{source.built_in ? `内置连接器 · ${source.connector}` : source.kind === "paid" ? "付费来源 · 本机凭据" : "免费网页来源"}</p></div></div><div className="source-url">{source.base_url}</div><div className={`source-health ${source.status}`}><i />{source.status === "available" ? "可访问" : source.status === "unavailable" ? "连接失败" : "未检测"}<small>{source.last_checked_at ? formatDate(source.last_checked_at) : ""}</small></div>{source.has_credentials && <span className="credential-chip">{source.username} · {source.masked_secret}</span>}<div className="source-actions"><button onClick={() => check(source)}>检测</button><button onClick={() => toggle(source)}>{source.enabled ? "停用" : "启用"}</button>{!source.built_in && (deleteId === source.id ? <span className="inline-confirm"><button className="danger-text" onClick={() => remove(source.id)}>确认删除</button><button onClick={() => setDeleteId("")}>取消</button></span> : <button className="danger-text" onClick={() => setDeleteId(source.id)}>删除</button>)}</div></article>)}</div>
  </>;
}

function ThemePanel() {
  const [theme, setTheme] = useState(() => loadTheme());
  const [selected, setSelected] = useState(() => THEME_PRESETS.some(item => item.name === loadTheme().name) ? loadTheme().name : "custom");
  const [status, setStatus] = useState({ kind: "", text: "" });
  const importRef = useRef(null);
  const commit = (next, selection = "custom") => {
    const saved = saveTheme({ ...next, name: selection === "custom" ? "自定义主题" : selection });
    applyTheme(saved); setTheme(saved); setSelected(selection); setStatus({ kind: "success", text: "外观已保存并应用到整个工作台" });
  };
  const choose = item => commit({ ...item.theme, type: theme.type }, item.name);
  const chooseType = type => commit({ ...theme, type }, selected);
  const update = (section, key, value) => commit({ ...theme, [section]: { ...theme[section], [key]: value } });
  const reset = () => commit(DEFAULT_THEME, DEFAULT_THEME.name);
  const exportTheme = () => {
    const blob = new Blob([JSON.stringify(theme, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "research-agent-theme.json"; anchor.click(); URL.revokeObjectURL(url);
  };
  const importTheme = async event => {
    const file = event.target.files?.[0]; if (!file) return;
    try { commit(parseThemeImport(await file.text())); setStatus({ kind: "success", text: "主题文件已验证并应用" }); }
    catch (error) { setStatus({ kind: "error", text: `导入失败：${error.message}` }); }
    event.target.value = "";
  };
  return <>
    <SectionHeading title="界面主题工作室" text="颜色、字体、布局和动效都由同一份主题配置控制" actions={<div className="theme-heading-actions"><button className="secondary-action compact-action" onClick={exportTheme}>导出 JSON</button><button className="secondary-action compact-action" onClick={() => importRef.current?.click()}>导入 JSON</button><button className="secondary-action compact-action" onClick={reset}>恢复默认</button><input ref={importRef} type="file" accept="application/json,.json" onChange={importTheme} hidden /></div>} />
    {status.text && <div className={`settings-alert ${status.kind}`}>{status.text}</div>}
    <div className="palette-grid">{THEME_PRESETS.map(item => <button className={`palette-card ${selected === item.name ? "active" : ""}`} key={item.name} onClick={() => choose(item)}><span className="palette-preview">{Object.values(item.theme.colors).slice(0, 5).map((color, index) => <i key={`${color}-${index}`} style={{ background: color }} />)}</span><strong>{item.name}</strong><small>{item.note}</small></button>)}</div>
    <section className="theme-type-block">
      <header><div><span>Type</span><h2>界面类型</h2><p>类型只改变操作界面的形态，不锁定颜色。上面的色板和下方自定义颜色都会继续生效。</p></div></header>
      <div className="theme-type-grid">{THEME_TYPES.map(item => <button type="button" className={`theme-type-card ${theme.type === item.value ? "active" : ""} type-${item.value}`} key={item.value} onClick={() => chooseType(item.value)}><span className="type-preview" aria-hidden="true"><i /><i /><i /><i /></span><strong>{item.label}</strong><small>{item.note}</small></button>)}</div>
    </section>
    <section className="custom-theme-card"><header><div><h2>全局颜色</h2><p>修改后立即覆盖所有页面、卡片、图表和状态</p></div>{selected === "custom" && <span>正在使用自定义主题</span>}</header><div className="color-fields">{COLOR_FIELDS.map(([key, label]) => <label key={key}><span>{label}</span><input aria-label={label} type="color" value={theme.colors[key]} onChange={event => update("colors", key, event.target.value)} /><code>{theme.colors[key]}</code></label>)}</div></section>
    <div className="theme-studio-grid">
      <section className="theme-control-card"><header><h2>字体与比例</h2><p>标题保留 Sci Agent 的编辑部气质，正文优先保证可读性。</p></header><label>标题字体<select value={theme.typography.display} onChange={event => update("typography", "display", event.target.value)}>{FONT_OPTIONS.display.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>正文字体<select value={theme.typography.body} onChange={event => update("typography", "body", event.target.value)}>{FONT_OPTIONS.body.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>字号比例 <output>{theme.typography.scale.toFixed(2)}×</output><input type="range" min="0.85" max="1.25" step="0.05" value={theme.typography.scale} onChange={event => update("typography", "scale", Number(event.target.value))} /></label></section>
      <section className="theme-control-card"><header><h2>圆角与布局</h2><p>控制内容宽度、侧栏和整体紧凑程度。</p></header><label>内容最大宽度 <output>{theme.layout.contentWidth}px</output><input type="range" min="960" max="1680" step="40" value={theme.layout.contentWidth} onChange={event => update("layout", "contentWidth", Number(event.target.value))} /></label><label>侧栏宽度 <output>{theme.layout.sidebarWidth}px</output><input type="range" min="220" max="380" step="10" value={theme.layout.sidebarWidth} onChange={event => update("layout", "sidebarWidth", Number(event.target.value))} /></label><label>卡片圆角 <output>{theme.shape.cardRadius}px</output><input type="range" min="0" max="36" value={theme.shape.cardRadius} onChange={event => update("shape", "cardRadius", Number(event.target.value))} /></label><label>控件圆角 <output>{theme.shape.controlRadius}px</output><input type="range" min="0" max="24" value={theme.shape.controlRadius} onChange={event => update("shape", "controlRadius", Number(event.target.value))} /></label><label>面板圆角 <output>{theme.shape.panelRadius}px</output><input type="range" min="0" max="44" value={theme.shape.panelRadius} onChange={event => update("shape", "panelRadius", Number(event.target.value))} /></label><label>界面密度<select value={theme.layout.density} onChange={event => update("layout", "density", event.target.value)}><option value="compact">紧凑</option><option value="comfortable">舒适</option><option value="relaxed">宽松</option></select></label></section>
      <section className="theme-control-card"><header><h2>背景与动效</h2><p>不再使用固定的大圆光，所有效果均可关闭。</p></header><label>页面背景<select value={theme.effects.background} onChange={event => update("effects", "background", event.target.value)}><option value="solid">纯色</option><option value="grain">细颗粒</option><option value="gradient">柔和渐变</option></select></label><label>阴影强度<select value={theme.effects.shadow} onChange={event => update("effects", "shadow", event.target.value)}><option value="none">无阴影</option><option value="soft">柔和</option><option value="defined">清晰</option></select></label><label className="theme-check"><input type="checkbox" checked={theme.navigation.autoHide} onChange={event => update("navigation", "autoHide", event.target.checked)} /><span><strong>滚动时自动隐藏顶栏</strong><small>向下隐藏，向上立即出现</small></span></label><label className="theme-check"><input type="checkbox" checked={theme.navigation.motion} onChange={event => update("navigation", "motion", event.target.checked)} /><span><strong>界面过渡动画</strong><small>系统开启减少动态效果时仍会自动停用</small></span></label></section>
    </div>
  </>;
}

function Toggle({ checked, onChange, label, text, disabled = false }) {
  return <label className={`privacy-row ${disabled ? "disabled" : ""}`}><div><strong>{label}</strong><p>{text}</p></div><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} disabled={disabled} /><span className="toggle-track"><i /></span></label>;
}

function PrivacyPanel({ api }) {
  const [privacy, setPrivacy] = useState({ external_network_access: true, approval_required: true, log_retention_days: 30, mask_credentials: true });
  const [approvals, setApprovals] = useState([]);
  const [status, setStatus] = useState({ kind: "", text: "" });
  const [confirmClear, setConfirmClear] = useState(false);
  const load = useCallback(() => Promise.all([apiJson(`${api}/settings/privacy`), apiJson(`${api}/settings/approvals`)]).then(([settings, items]) => { setPrivacy(settings); setApprovals(items); }).catch(error => setStatus({ kind: "error", text: error.message })), [api]);
  useEffect(() => { load(); }, [load]);
  const save = async () => { setStatus({ kind: "checking", text: "正在保存并应用策略…" }); try { const value = await apiJson(`${api}/settings/privacy`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(privacy) }); setPrivacy(value); setStatus({ kind: "success", text: `策略已生效${value.pruned_records ? `，清理 ${value.pruned_records} 条过期日志` : ""}` }); } catch (error) { setStatus({ kind: "error", text: error.message }); } };
  const clear = async () => { try { const value = await apiJson(`${api}/settings/clear-logs`, { method: "POST" }); setConfirmClear(false); setStatus({ kind: "success", text: `已清空 ${value.cleared_files} 个调用日志文件` }); } catch (error) { setStatus({ kind: "error", text: error.message }); } };
  return <><SectionHeading title="权限与隐私" text="控制外部访问、人工审批和本地日志" actions={<button className="primary-action compact-action" onClick={save}>保存策略</button>} />{status.text && <div className={`settings-alert ${status.kind}`}>{status.text}</div>}<section className="privacy-card"><Toggle checked={privacy.external_network_access} onChange={value => setPrivacy(item => ({ ...item, external_network_access: value }))} label="允许外部网络访问" text="关闭后，文献检索、网页访问和数据源检测会被后端阻止" /><Toggle checked={privacy.approval_required} onChange={value => setPrivacy(item => ({ ...item, approval_required: value }))} label="敏感操作需要人工确认" text="保持开启时，Agent 会显示允许 / 拒绝卡片后才继续" /><Toggle checked={true} onChange={() => {}} disabled label="凭据始终脱敏" text="API Key 和付费数据源密码不会通过普通接口返回明文" /><label className="retention-row"><div><strong>调用日志保留时间</strong><p>保存设置时会清理早于该期限的 Provider 日志</p></div><input type="number" min="1" max="3650" value={privacy.log_retention_days} onChange={event => setPrivacy(item => ({ ...item, log_retention_days: event.target.value }))} /><span>天</span></label></section><section className="approval-history"><header><div><h2>最近审批记录</h2><p>允许和拒绝都保存在对应会话中</p></div><button onClick={load}>刷新</button></header><div>{approvals.slice(0, 12).map((item, index) => <article key={`${item.run_id}-${item.time}-${index}`}><span className={item.event === "approval_resolved" ? (item.approved ? "approved" : "rejected") : "waiting"}>{item.event === "approval_requested" ? "待确认" : item.approved ? "已允许" : "已拒绝"}</span><p><strong>{item.skill || "Agent 操作"}</strong><small>{item.summary || "无摘要"}</small></p><time>{formatDate(item.time)}</time></article>)}{!approvals.length && <div className="usage-empty-row">暂无审批记录</div>}</div></section><section className="danger-zone"><div><h2>清理用量日志</h2><p>只清空 Provider 调用统计，不删除会话和科研成果。</p></div>{confirmClear ? <span className="inline-confirm"><button className="danger-action" onClick={clear}>确认清空</button><button onClick={() => setConfirmClear(false)}>取消</button></span> : <button className="danger-action" onClick={() => setConfirmClear(true)}>清理日志</button>}</section></>;
}

function AccountPanel({ api, onAccountChange }) {
  const [account, setAccount] = useState({ display_name: "", institution: "", email: "", title: "", bio: "", avatar: "" });
  const [status, setStatus] = useState({ kind: "", text: "" });
  useEffect(() => { apiJson(`${api}/settings/account`).then(setAccount).catch(error => setStatus({ kind: "error", text: error.message })); }, [api]);
  const save = async event => { event.preventDefault(); setStatus({ kind: "checking", text: "正在保存…" }); try { const value = await apiJson(`${api}/settings/account`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(account) }); setAccount(value); onAccountChange?.(value); setStatus({ kind: "success", text: "账号资料已保存在本机" }); } catch (error) { setStatus({ kind: "error", text: error.message }); } };
  const set = key => event => setAccount(value => ({ ...value, [key]: event.target.value }));
  const initials = (account.display_name || "研").slice(0, 2);
  return <><SectionHeading title="账号信息" text="用于本机工作台展示，暂不连接外部用户系统" />{status.text && <div className={`settings-alert ${status.kind}`}>{status.text}</div>}<form className="account-card" onSubmit={save}><aside><span>{initials}</span><strong>{account.display_name || "本地科研用户"}</strong><small>Local profile</small></aside><div className="account-fields"><label>显示名称<input value={account.display_name} onChange={set("display_name")} placeholder="你的名称" /></label><label>单位 / 实验室<input value={account.institution} onChange={set("institution")} placeholder="学校、医院或实验室" /></label><label>邮箱<input type="email" value={account.email} onChange={set("email")} placeholder="仅保存在本机" /></label><label>职称 / 身份<input value={account.title} onChange={set("title")} placeholder="研究生、研究员、教师…" /></label><label className="wide-field">简介<textarea rows="5" value={account.bio} onChange={set("bio")} placeholder="研究方向或个人说明" /></label><footer className="wide-field"><span>后续接入外部账号系统时再增加登录、同步与服务器校验。</span><button className="primary-action">保存账号信息</button></footer></div></form></>;
}

export default function SettingsPage({ api, onAccountChange }) {
  const [section, setSection] = useState("quick");
  return <main className="settings-page page-frame"><aside className="settings-nav">{SECTIONS.map(([key, icon, label]) => <button key={key} className={section === key ? "active" : ""} onClick={() => setSection(key)}><Icon name={icon} size={18} />{label}</button>)}</aside><section className="settings-content">{section === "quick" && <QuickSetup api={api} />}{section === "usage" && <UsagePanel api={api} />}{section === "sources" && <DataSourcesPanel api={api} />}{section === "theme" && <ThemePanel />}{section === "privacy" && <PrivacyPanel api={api} />}{section === "account" && <AccountPanel api={api} onAccountChange={onAccountChange} />}</section></main>;
}
