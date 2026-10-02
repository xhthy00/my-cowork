/** @vitest-environment jsdom */
import { beforeEach, expect, it, vi } from "vitest";
import { startAppTask, syncAppTask, useAppTasks, watchAppTasks } from "../../renderer/src/api/industryAI";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useIndustryNavigation } from "../../renderer/src/store/industryNavigation";
import { getProjectRuntime } from "../../renderer/src/store/projectRuntime";

beforeEach(() => {
  useAppTasks.setState({ records: {}, error: "" });
  useIndustryNavigation.setState({ activeId: null, dirty: false, routes: {} });
  window.api = { ...window.api, backendRequest: undefined, getBackendUrl: vi.fn().mockResolvedValue("http://127.0.0.1:9000") } as unknown as typeof window.api;
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
    return new Response(JSON.stringify({ ...row, events: [], recovery: {cursor: 1,
      end: {type: "graph.end", task_id: row.task_id, status: "ok", summary: "恢复成功"}, pending_confirms: [], pending_questions: []} }));
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

it("restores historical business tasks without sending requests or changing their original dates", async () => {
  vi.useFakeTimers();
  const active = useSessionsStore.getState().createProject("当前草稿");
  const old = { task_id: "old-risk-task", status: "DONE", text: "分析任务风险", updated_at: 100,
    origin: { app_id: "cn.history", app_name: "任务与工时", project_id: "old-risk-project", space_id: "default", generation: "g", route: "/", context: {} } };
  useSessionsStore.getState().createProject(old.text, {id: old.origin.project_id, background: true, createdAt: 90_000, updatedAt: 100_000,
    initialMessages: [{id: "old-user", role: "user", content: old.text, createdAt: 91_000},
      {id: "old-answer", role: "assistant", content: "历史分析结果", createdAt: 100_000}]});
  const transport = vi.fn(async (url: string, _init?: RequestInit) => new Response(JSON.stringify(url.endsWith("industry-ai-tasks") ? { tasks: [old] } : {
    ...old, events: [{seq: 1, event: {type: "graph.start", task_id: old.task_id}},
      {seq: 2, event: {type: "graph.end", task_id: old.task_id, status: "ok", summary: "历史分析结果"}}],
  })));
  vi.stubGlobal("fetch", transport);
  const stop = watchAppTasks();
  try {
    await vi.advanceTimersByTimeAsync(10);
    const messages = getProjectRuntime(old.origin.project_id).session.getState().messages;
    expect(messages.map(message => message.createdAt)).toEqual([91_000, 100_000]);
    expect(useSessionsStore.getState().sessions.find(project => project.id === old.origin.project_id)).toMatchObject({createdAt: 90_000, updatedAt: 100_000, status: "done"});
    expect(useSessionsStore.getState().activeId).toBe(active);
    expect(getProjectRuntime(old.origin.project_id).session.getState().runStatus).toBe("done");
    expect(getProjectRuntime(old.origin.project_id).session.getState().trace).toEqual([]);
    await syncAppTask(old);
    expect(getProjectRuntime(old.origin.project_id).session.getState().messages).toHaveLength(2);
    expect(transport.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
    expect(transport.mock.calls.every(([url]) => !url.includes("/api/chat"))).toBe(true);
  } finally {stop(); vi.useRealTimers(); vi.unstubAllGlobals();}
});

it("keeps each restored turn at its own time and repairs startup-stamped cache dates", async () => {
  const origin = { app_id: "cn.turns", app_name: "业务", project_id: "history-turns", space_id: "default", generation: "g", route: "/", context: {} };
  useSessionsStore.getState().createProject("历史会话", {id: origin.project_id, background: true,
    initialMessages: [{id: "bad-date", role: "user", content: "第一问", createdAt: Date.now()}]});
  let task = {task_id: "history-turn-one", status: "DONE", text: "第一问", updated_at: 100, origin};
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({...task, events: [
    {seq: task.updated_at, event: {type: "graph.end", task_id: task.task_id, status: "ok", summary: `${task.text}答案`}},
  ]}))));
  try {
    await syncAppTask(task);
    task = {...task, task_id: "history-turn-two", text: "第二问", updated_at: 200};
    await syncAppTask(task);
    expect(getProjectRuntime(origin.project_id).session.getState().messages.map(message => message.createdAt)).toEqual([100_000, 100_000, 200_000, 200_000]);
    expect(useSessionsStore.getState().sessions.find(project => project.id === origin.project_id)?.updatedAt).toBe(200_000);
  } finally {vi.unstubAllGlobals();}
});

it("loads all 1731 historical events without showing a completed task as answering between pages", async () => {
  const task = { task_id: "paged-history", status: "DONE", text: "旧任务", updated_at: 100,
    origin: { app_id: "cn.pages", app_name: "任务与工时", project_id: "paged-project", space_id: "default", generation: "g", route: "/", context: {} } };
  useSessionsStore.getState().createProject(task.text, { id: task.origin.project_id, background: true,
    initialMessages: [{ id: "cached-answer", role: "assistant", content: "完整旧答案", createdAt: 100_000 }] });
  const runtime = getProjectRuntime(task.origin.project_id);
  runtime.session.setState({messages: useSessionsStore.getState().getMessages(task.origin.project_id)});
  runtime.session.getState().beginRun(); // stale display left by an earlier recovery
  const events = Array.from({length: 1731}, (_, i) => ({seq: i + 1, event: i === 0
    ? {type: "graph.start", task_id: task.task_id}
    : i === 1730 ? {type: "graph.end", task_id: task.task_id, status: "ok", summary: "完整旧答案"}
    : {type: "step.delta", task_id: task.task_id, agent_id: "single_agent", delta: "字"}}));
  const offsets: number[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const after = Number(new URL(url).searchParams.get("after"));
    offsets.push(after);
    expect(runtime.session.getState().runStatus).toBe("done");
    expect(runtime.session.getState().taskStartedAt).toBeNull();
    expect(runtime.session.getState().messages[0].content).toBe("完整旧答案");
    return new Response(JSON.stringify({...task, events: events.slice(after, after + 500)}));
  }));
  try {
    await syncAppTask(task);
    expect(offsets).toEqual([0, 500, 1000, 1500]);
    expect(runtime.session.getState().trace).toHaveLength(1731);
    expect(runtime.session.getState().messages.at(-1)?.content).toBe("完整旧答案");
    expect(runtime.session.getState()).toMatchObject({runStatus: "done", thinking: null, taskStartedAt: null});
    expect(useSessionsStore.getState().sessions.find(row => row.id === task.origin.project_id)).toMatchObject({status: "done", updatedAt: 100_000});
  } finally { vi.unstubAllGlobals(); }
});

it("keeps completed history stopped and intact if a later page fails, then retries it in full", async () => {
  const task = { task_id: "page-retry", status: "DONE", text: "旧分析", updated_at: 100,
    origin: { app_id: "cn.pages", app_name: "业务", project_id: "page-retry-project", space_id: "default", generation: "g", route: "/", context: {} } };
  useSessionsStore.getState().createProject(task.text, {id: task.origin.project_id, background: true,
    initialMessages: [{id: "cached", role: "assistant", content: "已有答案"}]});
  const runtime = getProjectRuntime(task.origin.project_id);
  runtime.session.setState({messages: useSessionsStore.getState().getMessages(task.origin.project_id)});
  const events = Array.from({length: 1001}, (_, i) => ({seq: i + 1, event: i === 0
    ? {type: "graph.start", task_id: task.task_id}
    : i === 1000 ? {type: "graph.end", task_id: task.task_id, status: "ok", summary: "已有答案"}
    : {type: "llm.heartbeat", task_id: task.task_id}}));
  let fail = true;
  const offsets: number[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const after = Number(new URL(url).searchParams.get("after"));
    offsets.push(after);
    if (after === 1000 && fail) throw new Error("读取失败");
    return new Response(JSON.stringify({...task, events: events.slice(after, after + 500)}));
  }));
  try {
    await expect(syncAppTask(task)).rejects.toThrow("读取失败");
    expect(runtime.session.getState()).toMatchObject({runStatus: "done", trace: [], messages: [{id: "cached", content: "已有答案"}]});
    fail = false;
    await syncAppTask(task);
    expect(offsets).toEqual([0, 500, 1000, 0, 500, 1000]);
    expect(runtime.session.getState().trace).toHaveLength(1001);
    expect(runtime.session.getState().messages.filter(row => row.role === "user")).toHaveLength(1);
    expect(runtime.session.getState().runStatus).toBe("done");
  } finally {vi.unstubAllGlobals();}
});

it.each(["DONE", "FAILED", "CANCELLED", "INTERRUPTED"])("settles a %s snapshot even when its end event is missing", async status => {
  const task = {task_id: `missing-end-${status}`, status, text: "历史任务", updated_at: 100,
    origin: {app_id: "cn.ends", app_name: "业务", project_id: `missing-end-${status}`, space_id: "default", generation: "g", route: "/", context: {}}};
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify({...task, events: url.endsWith("after=0") ? [
    {seq: 1, event: {type: "graph.start", task_id: task.task_id}},
    {seq: 2, event: {type: "step.delta", task_id: task.task_id, agent_id: "single_agent", delta: "</think>已保存的部分答案"}},
  ] : []}))));
  try {
    await syncAppTask(task);
    const runtime = getProjectRuntime(task.origin.project_id);
    expect(runtime.session.getState()).toMatchObject({runStatus: ["FAILED", "INTERRUPTED"].includes(status) ? "error" : "done", thinking: null, taskStartedAt: null});
    expect(runtime.session.getState().messages.some(row => row.content.includes("已保存的部分答案"))).toBe(true);
    const count = runtime.session.getState().messages.length;
    await syncAppTask(task);
    expect(runtime.session.getState().messages).toHaveLength(count);
    expect(runtime.session.getState().trace.filter(row => row.type === "graph.end")).toHaveLength(1);
  } finally {vi.unstubAllGlobals();}
});

it("continues showing a genuinely running task waiting for input", async () => {
  const task = {task_id: "live-waiting", status: "RUNNING", text: "新任务", updated_at: 100,
    origin: {app_id: "cn.ends", app_name: "业务", project_id: "live-waiting", space_id: "default", generation: "g", route: "/", context: {}}};
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({...task, waiting: true, events: [
    {seq: 1, event: {type: "graph.start", task_id: task.task_id}},
    {seq: 2, event: {type: "human.ask", task_id: task.task_id, question_id: "live-question", question: "请补充信息"}},
  ]}))));
  try {
    await syncAppTask(task);
    expect(getProjectRuntime(task.origin.project_id).session.getState().runStatus).toBe("running");
    expect(getProjectRuntime(task.origin.project_id).session.getState().messages.at(-1)?.humanQuestion?.status).toBe("pending");
    expect(useAppTasks.getState().records[task.task_id].waiting).toBe(true);
  } finally {vi.unstubAllGlobals();}
});

it("restores a large history with one compact request and no trace or per-token cache writes", async () => {
  const task = {task_id: "compact-history", status: "DONE", text: "历史任务", updated_at: 100,
    origin: {app_id: "cn.compact", app_name: "业务", project_id: "compact-history", space_id: "default", generation: "g", route: "/", context: {}}};
  useSessionsStore.getState().createProject(task.text, {id: task.origin.project_id, background: true,
    initialMessages: [{id: "cached-u", role: "user", content: task.text, createdAt: 90_000},
      {id: "cached-a", role: "assistant", content: "原答案", createdAt: 100_000}]});
  const persist = vi.spyOn(Storage.prototype, "setItem");
  const transport = vi.fn(async (url: string) => {
    expect(url.includes("recovery=true") || url.includes("after=5000")).toBe(true);
    return new Response(JSON.stringify({...task, events: [], recovery: {cursor: 5000,
      end: {type: "graph.end", summary: "完整历史答案", status: "ok"}, pending_confirms: [], pending_questions: []}}));
  });
  vi.stubGlobal("fetch", transport);
  try {
    await syncAppTask(task, {recovery: true});
    const state = getProjectRuntime(task.origin.project_id).session.getState();
    expect(transport).toHaveBeenCalledTimes(1);
    expect(state).toMatchObject({trace: [], traceNodes: [], traceEdges: [], runStatus: "done", thinking: null});
    expect(state.messages.map(message => message.content)).toEqual([task.text, "完整历史答案"]);
    expect(state.messages.map(message => message.createdAt)).toEqual([90_000, 100_000]);
    expect(persist.mock.calls.filter(([key]) => key === "my-cowork-sessions").length).toBeLessThan(10);
    await syncAppTask(task);
    expect(getProjectRuntime(task.origin.project_id).session.getState().trace).toEqual([]);
    expect(getProjectRuntime(task.origin.project_id).session.getState().messages).toHaveLength(2);
  } finally {persist.mockRestore(); vi.unstubAllGlobals();}
});

it("restores only active input requests, then follows new events from the recovery cursor", async () => {
  const task = {task_id: "compact-running", status: "RUNNING", text: "继续任务", updated_at: 100,
    origin: {app_id: "cn.compact", app_name: "业务", project_id: "compact-running", space_id: "default", generation: "g", route: "/", context: {}}};
  const transport = vi.fn(async (url: string) => new Response(JSON.stringify(url.includes("recovery=true")
    ? {...task, events: [], waiting: true, recovery: {cursor: 1731, end: null,
      pending_confirms: [{call_id: "compact-confirm", tool: "run_shell", args: {command: "pwd"}}],
      pending_questions: [{question_id: "compact-question", question: "选择收件人", options: ["领导", "同事"]}]}}
    : {...task, status: "DONE", waiting: false, events: [{seq: 1732, event: {type: "graph.end", task_id: task.task_id, status: "ok", summary: "新的结果"}}]})));
  vi.stubGlobal("fetch", transport);
  try {
    await syncAppTask(task, {recovery: true});
    const runtime = getProjectRuntime(task.origin.project_id);
    expect(runtime.session.getState().trace).toEqual([]);
    expect(runtime.session.getState().messages.some(message => message.humanQuestion?.status === "pending")).toBe(true);
    expect(runtime.session.getState().confirmQueue).toHaveLength(1);
    await syncAppTask(task);
    expect(transport.mock.calls[1][0]).toContain("after=1731");
    expect(runtime.session.getState().trace.map(event => event.type)).toEqual(["graph.end"]);
    expect(runtime.session.getState().runStatus).toBe("done");
    expect(runtime.session.getState().confirmQueue).toEqual([]);
    expect(runtime.session.getState().messages.at(-1)?.content).toBe("新的结果");
  } finally {vi.unstubAllGlobals();}
});

it("keeps answered question records together with their final answer during compact recovery", async () => {
  const task = {task_id: "compact-answered", status: "DONE", text: "帮我写邮件", updated_at: 100,
    origin: {app_id: "cn.compact", app_name: "业务", project_id: "compact-answered", space_id: "default", generation: "g", route: "/", context: {}}};
  useSessionsStore.getState().createProject(task.text, {id: task.origin.project_id, background: true, initialMessages: [
    {id: "cached-question-u", role: "user", content: task.text},
    {id: "cached-question-a", role: "assistant", content: "写给谁？", humanQuestion: {question_id: "answered-question", task_id: task.task_id,
      agent: "single_agent", options: [], status: "answered", answer: "领导"}},
    {id: "cached-reply", role: "user", content: "领导", humanReplyTo: "answered-question"},
    {id: "cached-final", role: "assistant", content: "旧邮件内容"},
  ]});
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({...task, events: [], recovery: {cursor: 5000,
    end: {type: "graph.end", summary: "完整邮件内容"}, pending_confirms: [], pending_questions: []}}))));
  try {
    await syncAppTask(task, {recovery: true});
    const state = getProjectRuntime(task.origin.project_id).session.getState();
    expect(state.messages.map(message => message.content)).toEqual([task.text, "写给谁？", "领导", "完整邮件内容"]);
    expect(state.messages[1].humanQuestion?.status).toBe("answered");
    expect(state.trace).toEqual([]);
  } finally {vi.unstubAllGlobals();}
});
