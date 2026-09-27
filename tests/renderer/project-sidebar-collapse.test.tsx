/** @vitest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

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

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "展开历史会话" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("以前的对话")).not.toBeVisible();
    expect(screen.getByRole("button", { name: "新建对话" })).toBeVisible();
    expect(usePageTabStore.getState().projectHistoryCollapsed).toBe(true);
    expect(localStorage.getItem("my-cowork-page-tab")).toContain('"projectHistoryCollapsed":true');

    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    expect(usePageTabStore.getState().projectHistoryCollapsed).toBe(false);
    expect(screen.getByText("以前的对话")).toBeVisible();
  });
});
