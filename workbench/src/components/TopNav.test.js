import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot } from "react-dom/client";
import TopNav from "./TopNav";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("navigation hides while scrolling down and returns while scrolling up", async () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  let y = 0;
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => y });
  document.documentElement.dataset.navAutoHide = "true";

  await act(async () => root.render(<TopNav page="home" onNavigate={() => {}} account={{}} />));
  y = 120;
  await act(async () => window.dispatchEvent(new Event("scroll")));
  expect(container.querySelector(".top-nav").classList.contains("is-hidden")).toBe(true);

  y = 80;
  await act(async () => window.dispatchEvent(new Event("scroll")));
  expect(container.querySelector(".top-nav").classList.contains("is-hidden")).toBe(false);

  await act(async () => root.unmount());
});

test("navigation stays visible when auto hide is disabled", async () => {
  const container = document.createElement("div");
  const root = createRoot(container);
  let y = 0;
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => y });
  document.documentElement.dataset.navAutoHide = "false";
  await act(async () => root.render(<TopNav page="home" onNavigate={() => {}} account={{}} />));
  y = 200;
  await act(async () => window.dispatchEvent(new Event("scroll")));
  expect(container.querySelector(".top-nav").classList.contains("is-hidden")).toBe(false);
  await act(async () => root.unmount());
});
