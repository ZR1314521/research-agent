import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot } from "react-dom/client";
import { TextDecoder as NodeTextDecoder } from "util";
import App from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;
global.TextDecoder = NodeTextDecoder;

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
        { event: "assistant_delta", turn_id: "turn-a", sequence: 2, text: "A live answer" },
        { event: "turn_finished", turn_id: "turn-a", sequence: 3, assistant_message: "A live answer" },
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
  expect(container.textContent).toContain("A live answer");
  expect(container.textContent).not.toContain("B content");

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
