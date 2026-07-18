import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot } from "react-dom/client";
import { TextDecoder as NodeTextDecoder } from "util";

jest.mock("react-markdown", () => {
  const ReactRuntime = require("react");
  return ({ children, className }) => ReactRuntime.createElement("div", { className }, children);
});
jest.mock("remark-gfm", () => () => {});

import App, { outcomeStepStatus } from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;
global.TextDecoder = NodeTextDecoder;

test("tool outcomes map to distinct user-visible step states", () => {
  expect(outcomeStepStatus("success", true)).toBe("completed");
  expect(outcomeStepStatus("empty", false)).toBe("empty");
  expect(outcomeStepStatus("partial", true)).toBe("partial");
  expect(outcomeStepStatus("rate_limited", false)).toBe("rate_limited");
});

function jsonResponse(value) {
  return { ok: true, json: async () => value };
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function streamResponse(events) {
  const chunks = events.map(event => Uint8Array.from(Buffer.from(`${JSON.stringify(event)}\n`, "utf8")));
  let index = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => index < chunks.length
          ? { value: chunks[index++], done: false }
          : { value: undefined, done: true },
      }),
    },
  };
}

const run = (id, content) => ({
  run_id: id,
  status: "active",
  artifacts: {},
  messages: [{ role: "assistant", content }],
});

test("a late response from a previously selected conversation cannot replace the current one", async () => {
  window.history.replaceState(null, "", "#/home");
  const lateA = deferred();
  let aDetailCalls = 0;
  const sessions = [
    { run_id: "run-a", title: "Session A" },
    { run_id: "run-b", title: "Session B" },
  ];
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse(sessions));
    if (url.endsWith("/runs") && options.method === "POST") {
      return Promise.resolve(jsonResponse(run("run-a", "A created")));
    }
    if (url.endsWith("/runs/run-a")) {
      aDetailCalls += 1;
      return aDetailCalls === 1
        ? lateA.promise
        : Promise.resolve(jsonResponse(run("run-a", "A refreshed")));
    }
    if (url.endsWith("/runs/run-b")) {
      return Promise.resolve(jsonResponse(run("run-b", "B content")));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });

  const sessionB = [...container.querySelectorAll(".session-item")]
    .find(item => item.textContent.includes("Session B"));
  await act(async () => {
    sessionB.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(container.querySelector(".workspace-heading h1").textContent).toBe("Session B");
  expect(container.textContent).toContain("B content");

  await act(async () => {
    lateA.resolve(jsonResponse(run("run-a", "A stale content")));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(container.querySelector(".workspace-heading h1").textContent).toBe("Session B");
  expect(container.textContent).toContain("B content");
  expect(container.textContent).not.toContain("A stale content");

  await act(async () => root.unmount());
  container.remove();
});

test("a running conversation continues while the user visits another conversation", async () => {
  window.history.replaceState(null, "", "#/home");
  const sessions = [
    { run_id: "run-a", title: "Session A" },
    { run_id: "run-b", title: "Session B" },
  ];
  let aFinished = false;
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse(sessions));
    if (url.endsWith("/runs") && options.method === "POST") {
      return Promise.resolve(jsonResponse(run("run-a", "A created")));
    }
    if (url.includes("/runs/run-a/turns/turn-a/events")) {
      return Promise.resolve(streamResponse([
        { event: "turn_started", turn_id: "turn-a", sequence: 1 },
      ]));
    }
    if (url.endsWith("/runs/run-a")) {
      return Promise.resolve(jsonResponse(aFinished
        ? { ...run("run-a", "A finished in background"), status: "completed" }
        : { ...run("run-a", "A is working"), active_turn: { turn_id: "turn-a", status: "running" } }));
    }
    if (url.endsWith("/runs/run-b")) {
      return Promise.resolve(jsonResponse({ ...run("run-b", "B content"), status: "completed" }));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(container.textContent).toContain("A is working");

  const session = title => [...container.querySelectorAll(".session-item")]
    .find(item => item.textContent.includes(title));
  await act(async () => {
    session("Session B").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(container.querySelector(".workspace-heading h1").textContent).toBe("Session B");
  expect(container.textContent).toContain("B content");

  aFinished = true;
  await act(async () => {
    session("Session A").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(container.querySelector(".workspace-heading h1").textContent).toBe("Session A");
  expect(container.textContent).toContain("A finished in background");
  expect(global.fetch.mock.calls.some(([input]) => String(input).endsWith("/runs/run-a/cancel"))).toBe(false);

  await act(async () => root.unmount());
  container.remove();
});

test("returning to a running conversation reconnects to that turn", async () => {
  window.history.replaceState(null, "", "#/home");
  const sessions = [
    { run_id: "run-a", title: "Session A" },
    { run_id: "run-b", title: "Session B" },
  ];
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse(sessions));
    if (url.endsWith("/runs") && options.method === "POST") {
      return Promise.resolve(jsonResponse({ ...run("run-b", "B created"), status: "completed" }));
    }
    if (url.endsWith("/runs/run-b")) {
      return Promise.resolve(jsonResponse({ ...run("run-b", "B content"), status: "completed" }));
    }
    if (url.endsWith("/runs/run-a")) {
      return Promise.resolve(jsonResponse({
        ...run("run-a", "A persisted context"),
        active_turn: { turn_id: "turn-a", status: "running" },
      }));
    }
    if (url.includes("/runs/run-a/turns/turn-a/events")) {
      return Promise.resolve(streamResponse([
        { event: "turn_started", turn_id: "turn-a", sequence: 1 },
        { event: "assistant_delta", turn_id: "turn-a", sequence: 2, text: "正在检索资料" },
        { event: "turn_finished", turn_id: "turn-a", sequence: 3, assistant_message: "这是最终趋势结论" },
      ]));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });

  const sessionA = [...container.querySelectorAll(".session-item")]
    .find(item => item.textContent.includes("Session A"));
  await act(async () => {
    sessionA.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(global.fetch.mock.calls.some(([input]) => String(input).includes("/runs/run-a/turns/turn-a/events"))).toBe(true);
  expect(container.textContent).toContain("这是最终趋势结论");
  expect(container.textContent).not.toContain("正在检索资料");
  expect(container.textContent).not.toContain("B content");

  expect(container.querySelector(".run-inspector")).toBeNull();
  await act(async () => {
    container.querySelector(".task-details-button").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(container.querySelector(".run-inspector")).not.toBeNull();

  await act(async () => root.unmount());
  container.remove();
});

test("creating a conversation does not cancel the running conversation", async () => {
  window.history.replaceState(null, "", "#/home");
  let createCount = 0;
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse([{ run_id: "run-a", title: "Session A" }]));
    if (url.endsWith("/runs") && options.method === "POST") {
      createCount += 1;
      return Promise.resolve(jsonResponse(createCount === 1
        ? run("run-a", "A created")
        : run("run-c", "C created")));
    }
    if (url.endsWith("/runs/run-a")) {
      return Promise.resolve(jsonResponse({
        ...run("run-a", "A is working"),
        active_turn: { turn_id: "turn-a", status: "running" },
      }));
    }
    if (url.includes("/runs/run-a/turns/turn-a/events")) {
      return Promise.resolve(streamResponse([
        { event: "turn_started", turn_id: "turn-a", sequence: 1 },
      ]));
    }
    if (url.endsWith("/runs/run-c")) return Promise.resolve(jsonResponse(run("run-c", "C created")));
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".new-session-button").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(container.textContent).toContain("C created");
  expect(global.fetch.mock.calls.some(([input]) => String(input).endsWith("/runs/run-a/cancel"))).toBe(false);

  await act(async () => root.unmount());
  container.remove();
});

test("a paused conversation accepts an adjustment in the same turn", async () => {
  window.history.replaceState(null, "", "#/home");
  const pausedRun = {
    ...run("run-p", "Paused work"),
    status: "active",
    active_turn: { turn_id: "turn-p", status: "paused" },
  };
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/runs") && options.method === "POST") return Promise.resolve(jsonResponse(pausedRun));
    if (url.endsWith("/runs/run-p")) return Promise.resolve(jsonResponse(pausedRun));
    if (url.includes("/runs/run-p/turns/turn-p/events")) return Promise.resolve(streamResponse([]));
    if (url.endsWith("/runs/run-p/intervene") && options.method === "POST") {
      return Promise.resolve(jsonResponse({ run_id: "run-p", turn_id: "turn-p", status: "running" }));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  const textarea = container.querySelector(".message-composer textarea");
  expect(textarea.disabled).toBe(false);
  expect(textarea.placeholder).toContain("调整要求");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
    setter.call(textarea, "保留原图，再生成箱线图");
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".message-composer").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(global.fetch.mock.calls.some(([input]) => String(input).endsWith("/runs/run-p/intervene"))).toBe(true);
  expect(container.textContent).toContain("保留原图，再生成箱线图");

  await act(async () => root.unmount());
  container.remove();
});

test("approving a pending action renders the returned assistant message once", async () => {
  window.history.replaceState(null, "", "#/home");
  const waiting = {
    ...run("run-approval", "论文计划已经准备好"),
    status: "waiting_user",
    pending_action: { type: "plan_approval", summary: "是否开始执行？" },
  };
  const completed = {
    ...run("run-approval", "论文已经开始生成"),
    status: "active",
    assistant_message: "论文已经开始生成",
    pending_action: null,
  };
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/runs") && options.method === "POST") return Promise.resolve(jsonResponse(waiting));
    if (url.endsWith("/runs/run-approval")) return Promise.resolve(jsonResponse(waiting));
    if (url.endsWith("/runs/run-approval/approve")) return Promise.resolve(jsonResponse(completed));
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<App />); await Promise.resolve(); });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  });
  await act(async () => {
    container.querySelector(".approve-action").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve(); await Promise.resolve();
  });

  const matches = [...container.querySelectorAll(".message-content")]
    .filter(node => node.textContent.includes("论文已经开始生成"));
  expect(matches).toHaveLength(1);
  await act(async () => root.unmount());
  container.remove();
});

test("replayed stream sequences do not duplicate assistant text", async () => {
  window.history.replaceState(null, "", "#/home");
  const active = {
    ...run("run-sequence", "已有上下文"),
    active_turn: { turn_id: "turn-sequence", status: "running" },
  };
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/runs") && options.method === "POST") return Promise.resolve(jsonResponse(active));
    if (url.endsWith("/runs/run-sequence")) return Promise.resolve(jsonResponse(active));
    if (url.includes("/runs/run-sequence/turns/turn-sequence/events")) {
      return Promise.resolve(streamResponse([
        { event: "turn_started", turn_id: "turn-sequence", sequence: 1 },
        { event: "assistant_delta", turn_id: "turn-sequence", sequence: 2, text: "唯一增量" },
        { event: "assistant_delta", turn_id: "turn-sequence", sequence: 2, text: "唯一增量" },
      ]));
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<App />); await Promise.resolve(); });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  });

  expect(container.textContent.match(/唯一增量/g)).toHaveLength(1);
  await act(async () => root.unmount());
  container.remove();
});

test("auto approval is an explicit per-session control", async () => {
  window.history.replaceState(null, "", "#/home");
  const manual = { ...run("run-auto", "准备就绪"), approval_mode: "manual" };
  const automatic = { ...manual, approval_mode: "auto" };
  global.fetch = jest.fn((input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/styles")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/settings/account")) return Promise.resolve(jsonResponse({}));
    if (url.endsWith("/sessions")) return Promise.resolve(jsonResponse([]));
    if (url.endsWith("/runs") && options.method === "POST") return Promise.resolve(jsonResponse(manual));
    if (url.endsWith("/runs/run-auto")) return Promise.resolve(jsonResponse(manual));
    if (url.endsWith("/runs/run-auto/approval-mode")) return Promise.resolve(jsonResponse(automatic));
    throw new Error(`Unexpected fetch: ${url}`);
  });

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<App />); await Promise.resolve(); });
  await act(async () => {
    container.querySelector(".chat-cta").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  });
  expect(container.querySelector(".auto-mode-toggle").textContent).toContain("Auto 关闭");
  await act(async () => {
    container.querySelector(".auto-mode-toggle").dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve(); await Promise.resolve();
  });
  expect(container.querySelector(".auto-mode-toggle").textContent).toContain("Auto 已开启");
  expect(global.fetch.mock.calls.some(([input]) => String(input).endsWith("/approval-mode"))).toBe(true);
  await act(async () => root.unmount());
  container.remove();
});
