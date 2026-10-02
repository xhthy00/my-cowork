/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import ScheduleView from "../../renderer/src/components/schedule/ScheduleView";
import HomeHub from "../../renderer/src/components/hub/HomeHub";
import { usePageTabStore } from "../../renderer/src/store/pageTab";

const base = "http://127.0.0.1:8765";
const json = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body });

let originalFetch: typeof fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  window.api = { getBackendUrl: vi.fn().mockResolvedValue(base) } as unknown as typeof window.api;
});

afterEach(() => { globalThis.fetch = originalFetch; });

it("uses a single automation toolbar and filters tasks without creating a project", async () => {
  const tasks = ["每日资讯简报", "每周工作总结"].map((title, index) => ({
    id: `auto-${index}`, title, instructions: title, enabled: false,
    schedule_label: "每天 09:00", next_run: null, last_status: "ok", run_count: 7,
  }));
  globalThis.fetch = vi.fn().mockResolvedValue(json({ tasks })) as unknown as typeof fetch;
  usePageTabStore.setState({homeSection: "triggers"});
  render(<HomeHub />);
  await screen.findByRole("button", {name: /每日资讯简报.*下次/});
  expect(screen.getAllByRole("button", {name: "新建", exact: true})).toHaveLength(1);
  expect(screen.queryByRole("tab", {name: /空间|项目|触发器/})).toBeNull();
  fireEvent.change(screen.getByRole("textbox", {name: "搜索自动化任务"}), {target: {value: "工作总结"}});
  expect(screen.getByRole("button", {name: /每周工作总结.*下次/})).toBeInTheDocument();
  expect(screen.queryByRole("button", {name: /每日资讯简报.*下次/})).toBeNull();
  fireEvent.change(screen.getByRole("textbox", {name: "搜索自动化任务"}), {target: {value: "不存在"}});
  expect(screen.getByRole("status")).toHaveTextContent("没有匹配的任务");
  fireEvent.click(screen.getByRole("button", {name: "新建", exact: true}));
  expect(screen.getByLabelText("任务名称")).toBeInTheDocument();
});

it("creates a task from labeled fields and converts weekly time to standard cron", async () => {
  const created = {
    id: "auto-test", title: "周报", instructions: "整理周报", source: "user",
    schedule: { kind: "cron", cron: "30 9 * * 1", timezone: "local" },
    schedule_label: "30 9 * * 1", enabled: true, next_run: 1, last_run: null,
    last_status: null, run_count: 0, unseen_runs: 0, unseen_failed: false,
    notify_on_completion: true,
  };
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/automations") && init?.method === "POST") return Promise.resolve(json({ ok: true, task: created }, 201));
    if (url.endsWith("/api/automations")) return Promise.resolve(json({ tasks: [] }));
    if (url.endsWith("/api/automations/auto-test/seen")) return Promise.resolve(json({ ok: true }));
    if (url.endsWith("/api/automations/auto-test")) return Promise.resolve(json({ task: created, runs: [] }));
    return Promise.resolve(json({}));
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  render(<ScheduleView />);
  fireEvent.click(screen.getByRole("button", { name: "新建" }));
  fireEvent.change(screen.getByLabelText("任务名称"), { target: { value: "周报" } });
  fireEvent.change(screen.getByLabelText("执行内容"), { target: { value: "整理周报" } });
  fireEvent.change(screen.getByLabelText("执行频率"), { target: { value: "weekly" } });
  fireEvent.change(screen.getByLabelText("每天的时间"), { target: { value: "09:30" } });
  fireEvent.click(screen.getByText("高级：执行授权"));
  fireEvent.change(screen.getByLabelText("允许的完整命令"), { target: { value: "git status --short" } });
  fireEvent.click(screen.getByRole("button", { name: "添加命令" }));
  fireEvent.click(screen.getByRole("checkbox", { name: /自动批准此任务的命令与浏览器交互/ }));
  fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    `${base}/api/automations`,
    expect.objectContaining({ method: "POST" }),
  ));
  const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(createCall?.[1]?.body as string)).toMatchObject({
    title: "周报", instructions: "整理周报",
    schedule: { kind: "cron", cron: "30 9 * * 1", timezone: "local" },
    always_allowed_commands: ["git status --short"],
    auto_approve_commands: true,
  });
});

it("can remember an exact command for future runs before resuming", async () => {
  const task = {
    id: "auto-shell", title: "检查仓库", instructions: "检查状态", source: "user",
    schedule: { kind: "cron", cron: "0 9 * * *", timezone: "local" },
    schedule_label: "0 9 * * *", enabled: true, next_run: 1, last_run: null,
    last_status: "waiting_user", run_count: 1, unseen_runs: 0, unseen_failed: false,
    notify_on_completion: false, always_allowed_commands: [],
  };
  const run = {
    run_id: "run-shell", task_id: task.id, task_execution_id: "graph-shell",
    session_id: "__run__run-shell", trigger: "manual", started_at: 1,
    finished_at: null, status: "waiting_user", result_text: "", artifacts: [], error: null,
  };
  const calls: string[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") { calls.push("patch"); return Promise.resolve(json({ ok: true, task })); }
    if (url.endsWith("/api/tool/confirm/call-shell")) { calls.push("confirm"); return Promise.resolve(json({ ok: true })); }
    if (url.endsWith("/api/automations/auto-shell/runs/run-shell")) return Promise.resolve(json({ run, events: [{ type: "tool.confirm_request", call_id: "call-shell", tool: "exec.bash", args: { cmd: "git status --short", cwd: "/tmp/work" } }] }));
    if (url.endsWith("/api/automations/auto-shell/seen")) return Promise.resolve(json({ ok: true }));
    if (url.endsWith("/api/automations/auto-shell")) return Promise.resolve(json({ task, runs: [run] }));
    return Promise.resolve(json({ tasks: [task] }));
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  render(<ScheduleView />);
  fireEvent.click(await screen.findByRole("button", { name: /检查仓库.*下次/ }));
  fireEvent.click(await screen.findByRole("button", { name: /手动运行/ }));
  fireEvent.click(await screen.findByRole("button", { name: "此任务以后允许这条命令" }));
  await waitFor(() => expect(calls).toEqual(["patch", "confirm"]));
  expect(fetchMock).toHaveBeenCalledWith(`${base}/api/automations/auto-shell`, expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ add_command: "git status --short" }),
  }));
});

it("shows a paused workforce plan and submits the user's confirmation", async () => {
  const task = {
    id: "auto-plan", title: "周报", instructions: "整理周报", source: "user",
    schedule: { kind: "cron", cron: "0 9 * * 1", timezone: "local" },
    schedule_label: "0 9 * * 1", enabled: true, next_run: 1, last_run: null,
    last_status: "waiting_user", run_count: 0, unseen_runs: 0, unseen_failed: false,
    notify_on_completion: false,
  };
  const run = {
    run_id: "run-plan", task_id: task.id, task_execution_id: "graph-plan",
    session_id: "__run__run-plan", trigger: "manual", started_at: 1,
    finished_at: null, status: "waiting_user", result_text: "", artifacts: [], error: null,
  };
  const subtasks = [{ title: "收集资料" }, { title: "写总结" }];
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/workforce/start")) return Promise.resolve(json({ ok: true }));
    if (url.endsWith("/api/automations/auto-plan/runs/run-plan")) return Promise.resolve(json({ run, events: [{ type: "to_sub_tasks", subtasks }] }));
    if (url.endsWith("/api/automations/auto-plan/seen")) return Promise.resolve(json({ ok: true }));
    if (url.endsWith("/api/automations/auto-plan")) return Promise.resolve(json({ task, runs: [run] }));
    return Promise.resolve(json({ tasks: [task] }));
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  render(<ScheduleView />);
  fireEvent.click(await screen.findByRole("button", { name: /周报.*下次/ }));
  fireEvent.click(await screen.findByRole("button", { name: /手动运行/ }));
  expect(await screen.findByText(/收集资料/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "确认方案并继续" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    `${base}/api/workforce/start`,
    expect.objectContaining({ method: "POST", body: JSON.stringify({ task_id: "graph-plan", subtasks }) }),
  ));
});
