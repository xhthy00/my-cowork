/** @vitest-environment jsdom */
import { beforeEach, expect, it, vi } from "vitest";
import { startAppTask, syncAppTask, useAppTasks, watchAppTasks, followupAppTask, isAppTaskRunning } from "../../renderer/src/api/industryAI";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useIndustryNavigation } from "../../renderer/src/store/industryNavigation";
import { getProjectRuntime } from "../../renderer/src/store/projectRuntime";

beforeEach(() => {
  useAppTasks.setState({ records: {}, error: "" });
  useIndustryNavigation.setState({ activeId: null, dirty: false, routes: {} });
  window.api = { ...window.api, backendRequest: undefined, getBackendUrl: vi.fn().mockResolvedValue("http://127.0.0.1:9000") } as unknown as typeof window.api;
});

it("keeps polling budget-paused executions", () => {
  expect(isAppTaskRunning({ status: "PAUSED" } as Parameters<typeof isAppTaskRunning>[0])).toBe(true);
});

it("uses the business conversation model and budget for followups", async () => {
  const parent = { task_id: "model-parent", status: "DONE", text: "分析", updated_at: 1,
    origin: { app_id: "cn.model", app_name: "业务", project_id: "model-project", space_id: "default", generation: "g", route: "", context: {} } };
  useSessionsStore.getState().createProject("业务", { id: "model-project", modelProfileId: "chosen-model", modelReasoning: { "chosen-model": { effort: "high" } }, taskBudget: { max_tokens: 450000 }, appOrigin: { appId: "cn.model", appName: "业务", route: "", taskId: parent.task_id, generation: "g" } });
  window.api = { ...window.api, industryStatus: vi.fn().mockResolvedValue({ generation: "g" }) } as typeof window.api;
  const fetch = vi.fn(async (_url: string, init?: RequestInit) => new Response(JSON.stringify(init?.method === "POST" ? { ...parent, task_id: "model-child" } : { ...parent, events: [] })));
  vi.stubGlobal("fetch", fetch);
  try {
    await followupAppTask("model-project", "继续");
    const sent = JSON.parse(String(fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body));
    expect(sent.model_profile_id).toBe("chosen-model");
    expect(sent.reasoning).toEqual({ effort: "high" });
    expect(sent.task_budget).toEqual({ max_tokens: 450000 });
  } finally { vi.unstubAllGlobals(); }
});

it("starts in the background and routes results to the business project only", async () => {
  const active = useSessionsStore.getState().createProject("原有工作");
  const first = { task_id: "task-one", status: "DONE", text: "分析风险", updated_at: 100, origin: { app_id: "cn.one", app_name: "业务一", project_id: "business-one", space_id: "default", generation: "g1", route: "/tasks/1", context: { selection: [1] } } };
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify(url.includes("?after=") ? { ...first, events: [{ seq: 1, event: { type: "graph.start", task_id: first.task_id } }, { seq: 2, event: { type: "graph.end", task_id: first.task_id, status: "ok", summary: "存在延期风险" } }], files: [] } : first), { status: 200, headers: { "Content-Type": "application/json" } })));
  const task = await startAppTask("cn.one", "g1", { prompt: "分析风险" }, "request-one");
  await syncAppTask(task);
  expect(useSessionsStore.getState().activeId).toBe(active);
  expect(getProjectRuntime(active).session.getState().messages).toEqual([]);
  expect(getProjectRuntime("business-one").session.getState().messages.some(message => message.content.includes("延期风险"))).toBe(true);
  expect(useSessionsStore.getState().sessions.find(project => project.id === "business-one")?.appOrigin?.taskId).toBe("task-one");
  vi.unstubAllGlobals();
});

it("keeps unsaved business input in place when leaving is declined", () => {
  usePageTabStore.setState({ workspaceView: "hub", hubTab: "workbench" });
  useIndustryNavigation.setState({ dirty: true });
  vi.spyOn(window, "confirm").mockReturnValue(false);
  usePageTabStore.getState().setWorkspaceView("workspace");
  expect(usePageTabStore.getState().workspaceView).toBe("hub");
  expect(useIndustryNavigation.getState().dirty).toBe(true);
  vi.mocked(window.confirm).mockReturnValue(true);
  usePageTabStore.getState().setWorkspaceView("workspace");
  expect(usePageTabStore.getState().workspaceView).toBe("workspace");
});

it("retries startup failures and continues restoring other records", async () => {
  vi.useFakeTimers();
  const task = (id: string) => ({ task_id: id, status: "DONE", text: id, updated_at: 1,
    origin: { app_id: "cn.retry", app_name: "重试", project_id: id, space_id: "default", generation: "g", route: "", context: {} } });
  let lists = 0, failedReads = 0;
  const fetch = vi.fn(async (url: string) => {
    if (url.endsWith("industry-ai-tasks")) {
      if (++lists === 1) return new Response("", { status: 503 });
      return new Response(JSON.stringify({ tasks: [task("recovered-second"), task("recovered-first")] }));
    }
    if (url.includes("recovered-first") && ++failedReads === 1) throw new Error("暂时断开");
    const row = task(url.includes("recovered-first") ? "recovered-first" : "recovered-second");
    return new Response(JSON.stringify({ ...row, events: [{ seq: 1, event: { type: "graph.end", task_id: row.task_id, status: "ok", summary: "恢复成功" } }] }));
  });
  vi.stubGlobal("fetch", fetch);
  const stop = watchAppTasks();
  try {
    await vi.advanceTimersByTimeAsync(1100);
    expect(getProjectRuntime("recovered-second").session.getState().messages.some(row => row.content.includes("恢复成功"))).toBe(true);
    await vi.advanceTimersByTimeAsync(1100);
    expect(getProjectRuntime("recovered-first").session.getState().messages.some(row => row.content.includes("恢复成功"))).toBe(true);
    expect(useAppTasks.getState().error).toBe("");
  } finally { stop(); vi.useRealTimers(); vi.unstubAllGlobals(); }
});

it("shows an explicit error when execution events could not be saved", async () => {
  const task = { task_id: "unsaved", status: "RUNNING", text: "分析", updated_at: 1,
    origin: { app_id: "cn.retry", app_name: "重试", project_id: "unsaved", space_id: "default", generation: "g", route: "", context: {} } };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ ...task, status: "FAILED", storage_error: "任务记录保存失败：disk full", events: [] }))));
  try {
    await syncAppTask(task);
    expect(useAppTasks.getState().records.unsaved.status).toBe("FAILED");
    expect(getProjectRuntime("unsaved").session.getState().messages.some(row => row.content.includes("disk full"))).toBe(true);
  } finally { vi.unstubAllGlobals(); }
});
