import { useMemo, useState } from "react";

function normalizeArtifacts(value) {
  return Object.entries(value || {}).map(([name, item]) => {
    const record = typeof item === "string" ? { path: item } : (item || {});
    return {
      name,
      path: String(record.path || ""),
      type: String(record.type || ""),
      label: String(record.label || name.replaceAll("_", " ")),
      summary: String(record.summary || ""),
      presentation: String(record.presentation || "internal"),
    };
  }).filter(item => item.path && ["primary", "supporting"].includes(item.presentation));
}

function isImage(item) {
  return item.type === "Image" || /\.(png|svg|jpe?g|webp)$/i.test(item.path);
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).pop() || path;
}

export default function ArtifactList({ api, runId, artifacts }) {
  const items = useMemo(() => normalizeArtifacts(artifacts), [artifacts]);
  const [previewFailures, setPreviewFailures] = useState(new Set());
  if (!items.length) return null;

  const primary = items.filter(item => item.presentation === "primary");
  const supporting = items.filter(item => item.presentation === "supporting");

  const cards = values => values.map(item => {
    const url = `${api}/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(item.name)}`;
    const preview = isImage(item) && !previewFailures.has(item.name);
    return (
      <article className={`artifact-card ${preview ? "image-artifact" : ""}`} key={item.name}>
        {preview && (
          <a href={url} target="_blank" rel="noreferrer" className="artifact-preview" aria-label={`打开 ${fileName(item.path)}`}>
            <img
              src={url}
              alt={fileName(item.path)}
              onError={() => setPreviewFailures(previous => new Set(previous).add(item.name))}
            />
          </a>
        )}
        <div className="artifact-details">
          <span className="artifact-kind">{isImage(item) ? "图表" : "成果"}</span>
          <strong>{item.label}</strong>
          {item.summary && <p>{item.summary}</p>}
          <small>{fileName(item.path)}</small>
          <a href={url} target="_blank" rel="noreferrer">打开文件</a>
        </div>
      </article>
    );
  });

  return (
    <div className="artifact-list" aria-label="任务成果">
      {cards(primary)}
      {supporting.length > 0 && <details className="supporting-artifacts"><summary>相关文件 {supporting.length}</summary><div>{cards(supporting)}</div></details>}
    </div>
  );
}
