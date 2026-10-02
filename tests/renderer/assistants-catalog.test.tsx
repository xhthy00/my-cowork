/** @vitest-environment jsdom */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AssistantsView from "../../renderer/src/components/hub/AssistantsView";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useSessionsStore } from "../../renderer/src/store/sessions";

const assistants = [
  { id: "word", name: "文档助手", description: "整理报告", category: "document", enabled_skills: ["docx"], prompts: ["写项目周报"], source: "builtin" },
  { id: "excel", name: "表格助手", description: "分析销售数据", category: "spreadsheet", enabled_skills: ["xlsx"], prompts: ["分析销售数据"], source: "builtin" },
];
beforeEach(() => {
  window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue("http://127.0.0.1:8000") };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: async () => ({ assistants }) }));
  usePageTabStore.setState({ workspaceView: "hub", hubTab: "agents" });
  useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("combines category and text filters, including an empty result", async () => {
  render(<AssistantsView />);
  const catalog = await screen.findByRole("region", { name: "办公助理" });
  await screen.findByRole("heading", { name: "文档助手" });
  fireEvent.click(within(screen.getByRole("group", { name: "助理分类" })).getByRole("button", { name: "表格" }));
  expect(within(catalog).queryByRole("heading", { name: "文档助手" })).toBeNull();
  expect(within(catalog).getByRole("heading", { name: "表格助手" })).toBeVisible();
  fireEvent.change(screen.getByRole("textbox", { name: "搜索助理" }), { target: { value: "报告" } });
  expect(screen.getByText("没有找到匹配的助理，试试其他关键词或分类。")).toBeVisible();
  fireEvent.click(within(screen.getByRole("group", { name: "助理分类" })).getByRole("button", { name: "全部" }));
  expect(within(catalog).getByRole("heading", { name: "文档助手" })).toBeVisible();
});

it("starts a task with its bound skills and selected recommended prompt", async () => {
  render(<AssistantsView />);
  await screen.findByRole("button", { name: "写项目周报" });
  vi.useFakeTimers();
  const fill = vi.fn();
  window.addEventListener("my-cowork:composer-fill", fill);
  fireEvent.click(screen.getByRole("button", { name: "写项目周报" }));
  expect(usePageTabStore.getState().workspaceView).toBe("workspace");
  const store = useSessionsStore.getState();
  expect(store.sessions.find(s => s.id === store.activeId)).toMatchObject({ assistantId: "word", enabledSkillIds: ["docx"] });
  vi.advanceTimersByTime(80);
  expect(fill.mock.calls[0][0].detail).toBe("写项目周报");
  window.removeEventListener("my-cowork:composer-fill", fill);
});
