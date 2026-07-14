import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot } from "react-dom/client";
import ApprovalDock from "./ApprovalDock";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("pending backend approval exposes persistent allow and reject actions", async () => {
  const resolve = jest.fn();
  const container = document.createElement("div");
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <ApprovalDock
        pending={{ type: "tool_approval", summary: "将写入科研结果文件" }}
        onResolve={resolve}
      />
    );
  });

  expect(container.textContent).toContain("将写入科研结果文件");
  const buttons = [...container.querySelectorAll("button")];
  expect(buttons.map(item => item.textContent)).toEqual(["拒绝", "允许并继续"]);

  await act(async () => buttons[0].dispatchEvent(new MouseEvent("click", { bubbles: true })));
  await act(async () => buttons[1].dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(resolve.mock.calls).toEqual([[false], [true]]);

  await act(async () => root.unmount());
});
