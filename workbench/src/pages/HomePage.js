import AdaptiveLogo from "../components/AdaptiveLogo";

const CAPABILITIES = [
  { icon: "⌕", title: "文献检索与筛选", text: "连接公开学术来源，递归检索、去重并筛选相关研究。" },
  { icon: "▤", title: "文献阅读与综述", text: "提取核心证据，整理文献矩阵并生成综述框架。" },
  { icon: "⌁", title: "实验数据分析", text: "检查数据质量、异常值与趋势，形成清晰分析结果。" },
  { icon: "▥", title: "科研图表生成", text: "根据数据和研究目标生成适合论文表达的图表。" },
  { icon: "§", title: "参考文献管理", text: "校对文献信息，并在多种引用格式之间转换。" },
  { icon: "✎", title: "文档写作与编辑", text: "阅读、修改和导出科研文档，保留证据与结构。" },
];

function TiltCard({ item, index }) {
  const move = event => {
    if (event.pointerType === "touch") return;
    const card = event.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - .5;
    const y = (event.clientY - rect.top) / rect.height - .5;
    card.style.setProperty("--tilt-x", `${(-y * 5).toFixed(2)}deg`);
    card.style.setProperty("--tilt-y", `${(x * 6).toFixed(2)}deg`);
    card.style.setProperty("--glow-x", `${((x + .5) * 100).toFixed(1)}%`);
    card.style.setProperty("--glow-y", `${((y + .5) * 100).toFixed(1)}%`);
  };
  const reset = event => {
    event.currentTarget.style.setProperty("--tilt-x", "0deg");
    event.currentTarget.style.setProperty("--tilt-y", "0deg");
  };
  return <article className={`capability-card tone-${index % 3}`} onPointerMove={move} onPointerLeave={reset} onBlur={reset} tabIndex="0"><span className="capability-glow" /><span className="capability-icon">{item.icon}</span><div><h3>{item.title}</h3><p>{item.text}</p></div><span className="capability-arrow">↗</span></article>;
}

export default function HomePage({ onStart }) {
  return (
    <main className="home-page page-frame">
      <section className="home-hero">
        <div className="hero-copy">
          <a className="partner-brand" href="https://maas.ai-yuanjing.com/" target="_blank" rel="noreferrer" aria-label="访问中国联通元景 MaaS 平台">
            <AdaptiveLogo src="/maas-brand.png" alt="中国联通与元景 MaaS 平台" />
          </a>
          <span className="eyebrow">面向科研人员的本地智能工作台</span>
          <h1>让科研流程更清晰、更专注</h1>
          <p>
            Research Agent 可以检索与阅读文献、分析实验数据、生成科研图表、
            整理参考文献并完成文档写作，让复杂工作集中在一个对话中完成。
          </p>
          <div className="hero-actions"><a className="join-cta" href="https://maas.ai-yuanjing.com/" target="_blank" rel="noreferrer"><span>Join Us</span><span aria-hidden="true">↗</span></a><button className="chat-cta" onClick={onStart}><span>Chat</span><span aria-hidden="true">→</span></button></div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <span className="organic-shape shape-one" />
          <span className="organic-shape shape-two" />
          <div className="paper-card paper-main">
            <span className="paper-search" />
            <i /><i /><i />
          </div>
          <div className="paper-card paper-chart">
            <span className="chart-axis" />
            <span className="chart-line" />
          </div>
          <div className="paper-card paper-note"><b>研究报告</b><i /><i /><i /></div>
          <div className="paper-card paper-network"><span>●</span><span>●</span><span>●</span></div>
          <span className="leaf-sprig sprig-left">⌇⌇</span>
          <span className="leaf-sprig sprig-right">⌇⌇</span>
        </div>
      </section>

      <section className="capability-section">
        <div className="section-heading">
          <span />
          <h2>一个 Agent，覆盖完整科研工作</h2>
          <span />
        </div>
        <div className="capability-grid">
          {CAPABILITIES.map((item, index) => <TiltCard item={item} index={index} key={item.title} />)}
        </div>
      </section>
      <footer className="home-footer"><span />Research Agent · 让科研更高效，让创造更专注<span /></footer>
    </main>
  );
}
