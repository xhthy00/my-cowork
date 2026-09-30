/** @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import HubView from "../../renderer/src/components/hub/HubView";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useIndustryNavigation } from "../../renderer/src/store/industryNavigation";

afterEach(() => vi.unstubAllGlobals());

it("returns to the hub navigation from the running app without keeping a second toolbar", async () => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  usePageTabStore.setState({ workspaceView: "hub", hubTab: "workbench" });
  useIndustryNavigation.setState({ activeId: "cn.test.one", dirty: false, routes: {} });
  window.api = { ...window.api, industryList: vi.fn().mockResolvedValue({ apps: [{ id: "cn.test.one", version: "1.0.0", enabled: true, status: "ready", generation: "g", manifest: { name: "业务应用", ui: { entry: "frontend/dist/index.html" } } }] }), onBackendReady: vi.fn().mockReturnValue(() => {}) };
  render(<HubView />);
  await screen.findByTitle("业务应用");
  expect(screen.queryByRole("tab", { name: "工作台" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "返回应用列表" }));
  expect(screen.getByRole("tab", { name: "工作台" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "打开 业务应用" })).toBeInTheDocument();
});

it("keeps the app list and navigation available when a task's source app was removed", async () => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  usePageTabStore.setState({ workspaceView: "hub", hubTab: "workbench" });
  useIndustryNavigation.setState({ activeId: "cn.removed", dirty: false, routes: {} });
  window.api = { ...window.api, industryList: vi.fn().mockResolvedValue({ apps: [] }), onBackendReady: vi.fn().mockReturnValue(() => {}) };
  render(<HubView />);
  expect(await screen.findByRole("tab", { name: "工作台" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("来源应用已移除");
  expect(screen.getByRole("button", { name: "安装 ZIP" })).toBeInTheDocument();
});
