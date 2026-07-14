import { useEffect, useMemo, useState } from "react";

const SECTIONS = [
  ["quick", "⚙", "快速设置"],
  ["models", "◉", "模型服务"],
  ["sources", "▤", "学术数据源"],
  ["research", "⌁", "科研偏好"],
  ["privacy", "◇", "权限与隐私"],
  ["system", "▣", "系统与诊断"],
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

export default function SettingsPage({ api }) {
  const [section, setSection] = useState("quick");
  const [presets, setPresets] = useState([]);
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [context, setContext] = useState("1000000");
  const [timeout, setTimeoutValue] = useState("300");
  const [concurrency, setConcurrency] = useState("1");
  const [advanced, setAdvanced] = useState(false);
  const [status, setStatus] = useState({ kind: "", text: "" });

  useEffect(() => {
    Promise.all([
      fetch(`${api}/setup/presets`).then(response => response.ok ? response.json() : []),
      fetch(`${api}/health`).then(response => response.ok ? response.json() : {}),
    ]).then(([items, health]) => {
      setPresets(items);
      const match = items.find(item => providerKey(item.name) === providerKey(health.provider));
      if (match) {
        setProvider(match.name); setBaseUrl(match.base_url || ""); setModel(health.model || match.model || ""); setContext(String(match.context || 1000000));
      } else if (health.provider || health.model) {
        setProvider(health.provider || "自定义"); setModel(health.model || "");
      }
    }).catch(() => setStatus({ kind: "error", text: "暂时无法读取当前配置" }));
  }, [api]);

  const links = useMemo(() => PROVIDER_LINKS[providerKey(provider)] || null, [provider]);
  const chooseProvider = value => {
    setProvider(value);
    const item = presets.find(preset => preset.name === value);
    if (item) { setBaseUrl(item.base_url || ""); setModel(item.model || ""); setContext(String(item.context || 1000000)); }
    setStatus({ kind: "", text: "" });
  };

  const testConnection = async () => {
    setStatus({ kind: "checking", text: "正在检查后端连接…" });
    try {
      const response = await fetch(`${api}/health`);
      if (!response.ok) throw new Error(response.statusText);
      setStatus({ kind: "success", text: "后端连接正常；新模型配置需保存并重启后生效" });
    } catch (error) {
      setStatus({ kind: "error", text: `连接失败：${error.message}` });
    }
  };

  const save = async () => {
    if (!provider || !baseUrl || !model || !apiKey) {
      setStatus({ kind: "error", text: "请完整填写服务商、API Key、Base URL 和模型名称" });
      return;
    }
    setStatus({ kind: "checking", text: "正在保存…" });
    try {
      const response = await fetch(`${api}/setup/apply`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          llm_provider: providerKey(provider) || provider.toLowerCase().split(" ")[0],
          llm_model: model, llm_base_url: baseUrl, llm_api_key: apiKey,
          context_window: context, llm_timeout: timeout, max_concurrency: concurrency,
        }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
      setStatus({ kind: "success", text: "配置已保存，请重启后端使其生效" });
    } catch (error) {
      setStatus({ kind: "error", text: `保存失败：${error.message}` });
    }
  };

  return (
    <main className="settings-page page-frame">
      <aside className="settings-nav">
        {SECTIONS.map(([key, icon, label]) => <button key={key} className={section === key ? "active" : ""} onClick={() => setSection(key)}><span>{icon}</span>{label}</button>)}
      </aside>
      <section className="settings-content">
        {section !== "quick" ? (
          <div className="settings-placeholder">
            <span>{SECTIONS.find(item => item[0] === section)?.[1]}</span>
            <h1>{SECTIONS.find(item => item[0] === section)?.[2]}</h1>
            <p>该设置模块将在下一阶段接入。当前不会保存或伪造任何配置。</p>
          </div>
        ) : (
          <>
            <div className="settings-heading"><h1>快速设置</h1><p>连接你的模型服务，即可开始使用</p></div>
            <section className="quick-setup-card">
              <div className="form-row provider-row">
                <label htmlFor="provider">模型服务提供商</label>
                <div className="field-stack">
                  <select id="provider" value={provider} onChange={event => chooseProvider(event.target.value)}>
                    <option value="">选择服务商</option>
                    {presets.map(item => <option value={item.name} key={item.name}>{item.name}</option>)}
                    <option value="自定义">自定义 OpenAI 兼容服务</option>
                  </select>
                  {links && <div className="provider-links"><a href={links.site} target="_blank" rel="noreferrer">官方网站 ↗</a><a href={links.key} target="_blank" rel="noreferrer">申请 API Key ↗</a><a href={links.docs} target="_blank" rel="noreferrer">官方文档 ↗</a></div>}
                </div>
              </div>
              <div className="form-row"><label htmlFor="api-key">API Key</label><div className="password-field"><input id="api-key" type={showKey ? "text" : "password"} value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder="输入后仅保存在本机配置中" /><button onClick={() => setShowKey(value => !value)} type="button">{showKey ? "隐藏" : "显示"}</button></div></div>
              <div className="form-row"><label htmlFor="base-url">Base URL</label><input id="base-url" value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" /></div>
              <div className="form-row"><label htmlFor="model-name">模型名称</label><input id="model-name" value={model} onChange={event => setModel(event.target.value)} placeholder="输入模型标识" /></div>
              <button className="advanced-toggle" onClick={() => setAdvanced(value => !value)}><span>高级选项</span><span>{advanced ? "⌃" : "⌄"}</span></button>
              {advanced && <div className="advanced-grid"><label>上下文长度<input value={context} onChange={event => setContext(event.target.value)} /></label><label>请求超时（秒）<input value={timeout} onChange={event => setTimeoutValue(event.target.value)} /></label><label>最大并发数<input type="number" min="1" max="10" value={concurrency} onChange={event => setConcurrency(event.target.value)} /></label></div>}
              <footer className="setup-actions">
                <span className={`connection-status ${status.kind}`}><i />{status.text || "填写配置后可以检查连接"}</span>
                <div><button className="secondary-action" onClick={testConnection}>测试连接</button><button className="primary-action" onClick={save}>保存并应用</button></div>
              </footer>
            </section>
          </>
        )}
      </section>
    </main>
  );
}
