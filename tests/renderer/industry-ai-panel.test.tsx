/** @vitest-environment jsdom */
import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import IndustryAIPanel from "../../renderer/src/components/hub/IndustryAIPanel";
import { useAppTasks } from "../../renderer/src/api/industryAI";
import { getProjectRuntime } from "../../renderer/src/store/projectRuntime";

it("resumes the exact budget-paused business execution from its detail panel", async () => {
  useAppTasks.setState({ error: "", records: { paused: { task_id: "paused", status: "PAUSED", text: "分析", updated_at: 1,
    origin: { app_id: "cn.paused", app_name: "业务", generation: "g", project_id: "paused", space_id: "default", route: "", context: {} } } } });
  getProjectRuntime("paused").session.setState({ budgetTokens: 210000, budgetMaxTokens: 200000, budgetRequiredTokens: 100 });
  window.api = { ...window.api, backendRequest: undefined, getBackendUrl: vi.fn().mockResolvedValue("http://127.0.0.1:9000") } as typeof window.api;
  const fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  try {
    render(<IndustryAIPanel appId="cn.paused" selectedId="paused" onSelect={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText(/业务 · 预算暂停/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "增加额度并继续" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("http://127.0.0.1:9000/api/chat/paused/budget/resume", expect.objectContaining({ method: "POST" })));
    expect(JSON.parse(String(fetch.mock.calls[0][1].body)).max_tokens).toBeGreaterThan(210100);
  } finally { vi.unstubAllGlobals(); }
});

it("keeps Escape available after opening a record from the list", async () => {
  useAppTasks.setState({ error: "", records: { keyboard: { task_id: "keyboard", status: "DONE", text: "分析范围", updated_at: 1,
    origin: { app_id: "cn.keyboard", app_name: "业务", generation: "g", project_id: "keyboard", space_id: "default", route: "", context: {} } } } });
  const close = vi.fn();
  function Panel() {
    const [selected, setSelected] = useState<string | null>(null);
    return <IndustryAIPanel appId="cn.keyboard" selectedId={selected} onSelect={setSelected} onClose={close} />;
  }
  render(<Panel />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /分析范围/ }));
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "收起 AI 记录" }));
  await user.keyboard("{Escape}");
  expect(close).toHaveBeenCalledOnce();
});

it("keeps actual operation status visible and folds technical results", async () => {
  useAppTasks.setState({ error: "", records: { output: { task_id: "output", status: "DONE", text: "创建子任务", updated_at: 1,
    origin: { app_id: "cn.output", app_name: "业务", generation: "g", project_id: "output", space_id: "default", route: "/", context: { selection: [1] }, dev_revision: "abcdef012345" },
    operations: [{ operation_id: "op", tool: "创建子任务", status: "completed", result: { saved_id: 2 } }] } } });
  render(<IndustryAIPanel appId="cn.output" selectedId="output" onSelect={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByText(/创建子任务 · 已返回结果/)).toBeInTheDocument();
  const result = screen.getByText(/"saved_id"/).closest("details")!;
  expect(result).not.toHaveAttribute("open");
  expect(screen.getByText(/abcdef012345/).closest("details")).not.toHaveAttribute("open");
  await userEvent.click(screen.getByText("执行详情"));
  expect(result).toHaveAttribute("open");
});

it("shows a pending confirmation without an extra processing hint", () => {
  useAppTasks.setState({ error: "", records: { waiting: { task_id: "waiting", status: "RUNNING", waiting: true, text: "保存记录", updated_at: 1,
    origin: { app_id: "cn.waiting", app_name: "业务", generation: "g", project_id: "waiting", space_id: "default", route: "/", context: {} } } } });
  getProjectRuntime("waiting").session.setState({ messages: [{ id: "confirm", role: "assistant", content: "", confirm: {
    call_id: "save", tool: "industry__cn_waiting__save", tool_title: "保存记录", args: { value: "记录" }, status: "pending",
  } }] });
  render(<IndustryAIPanel appId="cn.waiting" selectedId="waiting" onSelect={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByText(/业务 · 待处理/)).toBeInTheDocument();
  expect(screen.queryByText(/正在处理，可收起此面板/)).toBeNull();
  expect(screen.getByRole("button", { name: "本次允许" })).toBeInTheDocument();
});
