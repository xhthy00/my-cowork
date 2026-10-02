/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import TopBar from "../../renderer/src/components/shell/TopBar";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useIndustryNavigation } from "../../renderer/src/store/industryNavigation";

it("opens task search and restores the trigger focus on Escape", async () => {
  render(<TopBar />);
  const user = userEvent.setup();
  const trigger = screen.getByRole("button", { name: "搜索任务" });
  await user.click(trigger);
  expect(screen.getByRole("dialog", { name: "搜索任务" })).toBeVisible();
  expect(screen.getByRole("textbox", { name: "任务名称" })).toHaveFocus();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("leaves search shortcuts to the plugin while its host sidebar is hidden", () => {
  usePageTabStore.setState({ workspaceView: "hub", hubTab: "workbench" });
  useIndustryNavigation.setState({ activeId: "cn.test.plugin" });
  try {
    render(<TopBar />);
    expect(fireEvent.keyDown(window, { key: "k", ctrlKey: true, cancelable: true })).toBe(true);
    expect(screen.queryByRole("dialog", { name: "搜索任务" })).toBeNull();
  } finally {
    useIndustryNavigation.setState({ activeId: null });
    usePageTabStore.setState({ workspaceView: "workspace" });
  }
});
