import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot } from "react-dom/client";
import SettingsPage from "./SettingsPage";

global.IS_REACT_ACT_ENVIRONMENT = true;

function responseFor(url) {
  if (url.endsWith("/setup/presets")) return [];
  if (url.endsWith("/health")) return {};
  if (url.includes("/usage")) {
    return {
      summary: {},
      filters: { providers: [], models: [], statuses: [] },
      records: [],
      providers: [],
      models: [],
      trend: [],
    };
  }
  return {};
}

test("researcher can switch away from an async settings panel without a runtime error", async () => {
  global.fetch = jest.fn(async url => ({
    ok: true,
    json: async () => responseFor(String(url)),
  }));
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<SettingsPage api="http://local.test" />);
    await Promise.resolve();
  });

  const clickSection = async label => {
    const button = [...container.querySelectorAll(".settings-nav button")]
      .find(item => item.textContent.includes(label));
    await act(async () => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });
  };

  await clickSection("用量统计");
  await clickSection("色彩设计");
  expect(container.textContent).toContain("界面主题工作室");
  expect(container.textContent).toContain("全局颜色");
  expect(container.textContent).toContain("字体与比例");
  expect(container.textContent).toContain("圆角与布局");
  expect(container.textContent).toContain("背景与动效");

  await act(async () => root.unmount());
  container.remove();
});

test("usage view explains missing model prices without presenting a fake amount", async () => {
  global.fetch = jest.fn(async url => ({
    ok: true,
    json: async () => responseFor(String(url)),
  }));
  const container = document.createElement("div");
  const root = createRoot(container);

  await act(async () => {
    root.render(<SettingsPage api="http://local.test" />);
    await Promise.resolve();
  });
  const usage = [...container.querySelectorAll(".settings-nav button")]
    .find(item => item.textContent.includes("用量统计"));
  await act(async () => {
    usage.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await Promise.resolve();
  });

  expect(container.textContent).toContain("费用暂未估算");
  expect(container.textContent).toContain("未配置模型单价");

  await act(async () => root.unmount());
});

test("theme controls apply presets and background options to the whole document", async () => {
  localStorage.clear();
  global.fetch = jest.fn(async url => ({ ok: true, json: async () => responseFor(String(url)) }));
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => { root.render(<SettingsPage api="http://local.test" />); await Promise.resolve(); });

  const themeSection = [...container.querySelectorAll(".settings-nav button")]
    .find(item => item.textContent.includes("色彩设计"));
  await act(async () => themeSection.dispatchEvent(new MouseEvent("click", { bubbles: true })));

  const bluePreset = [...container.querySelectorAll(".palette-card")]
    .find(item => item.textContent.includes("雾蓝纸张"));
  await act(async () => bluePreset.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(document.documentElement.style.getPropertyValue("--theme-page")).toBe("#ebf1f2");

  const background = [...container.querySelectorAll(".theme-control-card select")]
    .find(item => [...item.options].some(option => option.value === "gradient"));
  await act(async () => {
    background.value = "solid";
    background.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(document.documentElement.dataset.background).toBe("solid");
  expect(JSON.parse(localStorage.getItem("research-agent-theme")).effects.background).toBe("solid");

  await act(async () => root.unmount());
});

test("pixel laboratory is an independent type and keeps custom colors live", async () => {
  localStorage.clear();
  global.fetch = jest.fn(async url => ({ ok: true, json: async () => responseFor(String(url)) }));
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => { root.render(<SettingsPage api="http://local.test" />); await Promise.resolve(); });

  const themeSection = [...container.querySelectorAll(".settings-nav button")]
    .find(item => item.textContent.includes("色彩设计"));
  await act(async () => themeSection.dispatchEvent(new MouseEvent("click", { bubbles: true })));

  expect(container.textContent).toContain("Type");
  const pixelType = [...container.querySelectorAll(".theme-type-card")]
    .find(item => item.textContent.includes("像素实验室"));
  await act(async () => pixelType.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(document.documentElement.dataset.themeType).toBe("pixel");

  const pageColor = container.querySelector('input[aria-label="页面背景"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(pageColor, "#123456");
    pageColor.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(document.documentElement.dataset.themeType).toBe("pixel");
  expect(document.documentElement.style.getPropertyValue("--theme-page")).toBe("#123456");
  expect(JSON.parse(localStorage.getItem("research-agent-theme")).type).toBe("pixel");

  await act(async () => root.unmount());
});
