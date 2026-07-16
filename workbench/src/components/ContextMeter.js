import React from "react";

const compact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function positiveNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

export default function ContextMeter({ modelName, contextSize, contextWindow }) {
  const used = positiveNumber(contextSize);
  const limit = positiveNumber(contextWindow);
  const hasWindow = limit > 0;
  const percent = hasWindow ? Math.min(100, Math.round((used / limit) * 10000) / 100) : 0;

  if (!modelName) return null;

  return (
    <div
      className={`context-meter ${hasWindow ? "" : "window-unknown"}`}
      aria-label={`上下文使用情况：${modelName}`}
      title={hasWindow
        ? `${used.toLocaleString()} / ${limit.toLocaleString()} tokens`
        : `${used.toLocaleString()} tokens`}
    >
      <strong>{modelName}</strong>
      {hasWindow && (
        <span className="context-meter-track" aria-hidden="true">
          <i className="context-meter-fill" style={{ width: `${percent}%` }} />
        </span>
      )}
      <small>{hasWindow ? `${compact.format(used)} / ${compact.format(limit)}` : `${compact.format(used)} 上下文`}</small>
    </div>
  );
}
