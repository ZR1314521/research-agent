import { statusInfo } from "./TaskCenterPage";

test("idle sessions are never presented as running with fake progress", () => {
  expect(statusInfo("active")).toMatchObject({ key: "idle", progress: null });
  expect(statusInfo("idle")).toMatchObject({ key: "idle", progress: null });
  expect(statusInfo("running")).toMatchObject({ key: "running", progress: null });
  expect(statusInfo("completed")).toMatchObject({ key: "completed", progress: 100 });
});
