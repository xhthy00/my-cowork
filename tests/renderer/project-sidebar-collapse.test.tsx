/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectSidebar from "../../renderer/src/components/shell/ProjectSidebar";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useSessionsStore } from "../../renderer/src/store/sessions";

describe("project sidebar history", () => {
  beforeEach(() => {
    usePageTabStore.setState({
      projectSidebarFolded: false,
      projectHistoryCollapsed: false,
      workspaceView: "workspace",
    });
    useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
    useSessionsStore.getState().createProject("以前的对话");
  });

  afterEach(() => {
    useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
    localStorage.removeItem("my-cowork-page-tab");
    localStorage.removeItem("my-cowork-sessions");
  });

  it("collapses the list, keeps new chat available, and remembers the setting", () => {
    render(<ProjectSidebar fill />);

    const toggle = screen.getByRole("button", { name: "收起历史会话" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("以前的对话")).toBeVisible();
    expect(screen.queryByRole("button", { name: "本地工作区" })).toBeNull();
    expect(screen.queryByRole("button", { name: "选择工作空间" })).toBeNull();

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "展开历史会话" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("以前的对话")).not.toBeVisible();
    expect(screen.getByRole("button", { name: "新建任务" })).toBeVisible();
    expect(usePageTabStore.getState().projectHistoryCollapsed).toBe(true);
    expect(localStorage.getItem("my-cowork-page-tab")).toContain('"projectHistoryCollapsed":true');

    fireEvent.click(screen.getByRole("button", { name: "新建任务" }));
    expect(usePageTabStore.getState().projectHistoryCollapsed).toBe(false);
    expect(screen.getByText("以前的对话")).toBeVisible();
  });
});

it("routes the shared sidebar to assistants, projects and automations", () => {
  usePageTabStore.setState({ projectSidebarFolded: false, workspaceView: "workspace", agentsSection: "sub-agents" });
  render(<ProjectSidebar fill />);
  expect(screen.queryByRole("button", { name: "助理", exact: true })).toBeNull();
  expect(screen.queryByRole("button", { name: "资料库", exact: true })).toBeNull();
  expect(screen.queryByRole("button", { name: "浏览器", exact: true })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "助理 · 技能 · 连接器" }));
  expect(usePageTabStore.getState()).toMatchObject({ workspaceView: "hub", hubTab: "agents", agentsSection: "sub-agents" });
  expect(screen.getByRole("button", { name: "助理 · 技能 · 连接器" })).toHaveAttribute("aria-current", "page");
  fireEvent.click(screen.getByRole("button", { name: "自动化" }));
  expect(usePageTabStore.getState()).toMatchObject({ hubTab: "home", homeSection: "triggers" });
  fireEvent.click(screen.getByRole("button", { name: "项目" }));
  expect(usePageTabStore.getState()).toMatchObject({ hubTab: "home", homeSection: "projects" });
  fireEvent.click(screen.getByRole("button", { name: "新建任务" }));
  expect(usePageTabStore.getState().workspaceView).toBe("workspace");
});

it("shows the installed version and opens settings from an icon-only footer", async () => {
  const original = window.api?.getUpdaterStatus;
  window.api = { ...window.api, getUpdaterStatus: vi.fn().mockResolvedValue({ state: "idle", currentVersion: "1.2.3" }) };
  usePageTabStore.setState({ projectSidebarFolded: false, workspaceView: "workspace", settingsOpen: false });
  try {
    render(<ProjectSidebar fill />);
    expect(screen.getByText("MyCoWork")).toBeVisible();
    expect(await screen.findByText("v1.2.3")).toBeVisible();
    const settings = screen.getByRole("button", { name: "设置" });
    expect(settings.textContent).toBe("");
    expect(settings.querySelector("img")).toBeNull();
    fireEvent.click(settings);
    expect(usePageTabStore.getState()).toMatchObject({ settingsOpen: true, workspaceView: "workspace" });
  } finally { window.api.getUpdaterStatus = original; }
});
