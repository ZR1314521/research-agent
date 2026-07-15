import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import ArtifactList from "./ArtifactList";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("image artifacts show a preview and an explicit path", async () => {
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
        },
      }}
    />
  ));

  const image = container.querySelector("img");
  expect(image).not.toBeNull();
  expect(image.getAttribute("src")).toContain("/runs/run-one/artifacts/chart_a1");
  expect(container.textContent).toContain("C:\\runs\\run-one\\artifacts\\charts\\chart_a1.png");

  await act(async () => root.unmount());
  container.remove();
});

test("non-image artifacts keep their file path without an image preview", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => root.render(
    <ArtifactList api="http://127.0.0.1:8877" runId="run-one" artifacts={{ report: { type: "AnalysisReport", path: "C:\\runs\\report.md" } }} />
  ));

  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toContain("C:\\runs\\report.md");

  await act(async () => root.unmount());
  container.remove();
});
