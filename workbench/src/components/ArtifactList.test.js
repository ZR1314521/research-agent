import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import ArtifactList from "./ArtifactList";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("image artifacts show a preview and a user-facing label", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => root.render(
    <ArtifactList
      api="http://127.0.0.1:8877"
      runId="run-one"
      artifacts={{
        chart_a1: {
          type: "Image",
          path: "C:\\runs\\run-one\\artifacts\\charts\\chart_a1.png",
          producer: "scientific-chart",
          presentation: "primary",
          label: "方法趋势图",
        },
      }}
    />
  ));

  const image = container.querySelector("img");
  expect(image).not.toBeNull();
  expect(image.getAttribute("src")).toContain("/runs/run-one/artifacts/chart_a1");
  expect(container.textContent).toContain("方法趋势图");
  expect(container.textContent).not.toContain("C:\\runs\\run-one\\artifacts");

  await act(async () => root.unmount());
  container.remove();
});

test("internal artifacts never appear in the user result list", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => root.render(
    <ArtifactList api="http://127.0.0.1:8877" runId="run-one" artifacts={{ raw: { type: "File", path: "C:\\runs\\papers_raw.json", presentation: "internal" } }} />
  ));

  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).not.toContain("papers_raw.json");

  await act(async () => root.unmount());
  container.remove();
});

test("supporting files stay collapsed until the user asks for details", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => root.render(
    <ArtifactList api="http://127.0.0.1:8878" runId="run-one" artifacts={{ matrix: {
      type: "EvidenceMatrix",
      path: "C:\\runs\\literature_matrix.md",
      presentation: "supporting",
      label: "证据矩阵",
    } }} />
  ));

  expect(container.querySelector("details.supporting-artifacts")).not.toBeNull();
  expect(container.querySelector("details.supporting-artifacts").open).toBe(false);
  expect(container.textContent).toContain("相关文件 1");

  await act(async () => root.unmount());
  container.remove();
});
