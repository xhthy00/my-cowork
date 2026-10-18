/** @vitest-environment jsdom */
import { act, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import SessionSidePanel from "../../renderer/src/components/session/SessionSidePanel";
import { dropAllProjectRuntimes } from "../../renderer/src/store/projectRuntime";
import { useSessionStore } from "../../renderer/src/store/session";
import { useWorkforceStore } from "../../renderer/src/store/workforce";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { SessionMode } from "../../renderer/src/types/workforce";

vi.mock("@/components/TracePanel", () => ({ default: () => null }));

beforeEach(() => {
  dropAllProjectRuntimes();
  usePageTabStore.setState({ sidePanelVisible: true });
  useWorkforceStore.getState().setSessionMode(SessionMode.SINGLE_AGENT);
  useSessionStore.getState().beginRun();
});

it("shows actual plan steps as soon as the official todo event arrives", () => {
  render(<SessionSidePanel />);
  expect(screen.getByText("尚未收到步骤规划")).toBeInTheDocument();
  expect(screen.queryByText("正在规划全局步骤…")).not.toBeInTheDocument();
  act(() => useSessionStore.getState().handleEvent({
    type: "todo_state",
    payload: { agent_id: "single_agent", todos: [
      { id: "todo_1", content: "核实资料", status: "in_progress" },
      { id: "todo_2", content: "撰写报告", status: "pending" },
    ] },
  }));
  expect(screen.queryByText("尚未收到步骤规划")).not.toBeInTheDocument();
  expect(screen.getByText("核实资料")).toBeInTheDocument();
  expect(screen.getByText("撰写报告")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "全局步骤完成进度" })).toHaveAttribute("aria-valuemax", "2");
});
