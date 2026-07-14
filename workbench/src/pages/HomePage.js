const CAPABILITIES = [
  { icon: "⌕", title: "文献检索与筛选", text: "连接公开学术来源，递归检索、去重并筛选相关研究。" },
  { icon: "▤", title: "文献阅读与综述", text: "提取核心证据，整理文献矩阵并生成综述框架。" },
  { icon: "⌁", title: "实验数据分析", text: "检查数据质量、异常值与趋势，形成清晰分析结果。" },
  { icon: "▥", title: "科研图表生成", text: "根据数据和研究目标生成适合论文表达的图表。" },
  { icon: "§", title: "参考文献管理", text: "校对文献信息，并在多种引用格式之间转换。" },
  { icon: "✎", title: "文档写作与编辑", text: "阅读、修改和导出科研文档，保留证据与结构。" },
];

export default function HomePage({ onStart }) {
  return (
    <main className="home-page page-frame">
      <section className="home-hero">
        <div className="hero-copy">
          <span className="eyebrow">面向科研人员的本地智能工作台</span>
          <h1>让科研流程更清晰、更专注</h1>
          <p>
            Research Agent 可以检索与阅读文献、分析实验数据、生成科研图表、
            整理参考文献并完成文档写作，让复杂工作集中在一个对话中完成。
          </p>
          <button className="chat-cta" onClick={onStart}>
            <span>Chat</span><span aria-hidden="true">→</span>
          </button>
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
          {CAPABILITIES.map((item, index) => (
            <article className={`capability-card tone-${index % 3}`} key={item.title}>
              <span className="capability-icon">{item.icon}</span>
              <div><h3>{item.title}</h3><p>{item.text}</p></div>
            </article>
          ))}
        </div>
      </section>
      <footer className="home-footer"><span />Research Agent · 让科研更高效，让创造更专注<span /></footer>
    </main>
  );
}
