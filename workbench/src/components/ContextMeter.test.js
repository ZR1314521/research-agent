import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import ContextMeter from "./ContextMeter";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("shows the configured model and live context ratio without fixed task quotas", async () => {
  const container = document.createElement("div");
  const root = createRoot(container);

  await act(async () => {
    root.render(<ContextMeter modelName="deepseek-v4-pro" contextSize={39800} contextWindow={1000000} />);
  });

  expect(container.textContent).toContain("deepseek-v4-pro");
  expect(container.textContent).toContain("39.8K / 1M");
  expect(container.querySelector(".context-meter-fill").style.width).toBe("3.98%");
  expect(container.textContent).not.toContain("模型调用");
  expect(container.textContent).not.toContain("任务 Token");

  await act(async () => root.unmount());
});

test("does not invent a percentage when the provider context window is unknown", async () => {
  const container = document.createElement("div");
  const root = createRoot(container);

  await act(async () => {
    root.render(<ContextMeter modelName="custom-model" contextSize={39800} contextWindow={0} />);
  });

  expect(container.textContent).toContain("39.8K 上下文");
  expect(container.querySelector(".context-meter-track")).toBeNull();

  await act(async () => root.unmount());
});
