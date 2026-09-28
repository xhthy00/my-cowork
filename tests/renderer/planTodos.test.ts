import { describe, expect, it } from "vitest";

import { planTodosFromQuery } from "../../renderer/src/lib/planTodos";
import { buildProgressItems, buildStepExecutionDetails } from "../../renderer/src/lib/progressFromTrace";
import { createWorkforceStore } from "../../renderer/src/store/workforce";

describe("planTodosFromQuery", () => {
  it("does not seed a fake planning step", () => {
    expect(planTodosFromQuery("帮我将这篇博客转成md文件")).toEqual([]);
  });
});

describe("buildProgressItems", () => {
  it("does not pass off tool events as planned progress", () => {
    expect(buildProgressItems([])).toEqual([]);
  });

  it("keeps global steps and substeps separate", () => {
    const items = buildProgressItems(
      [
        {
          id: "todo_1",
          content: "抓取文章",
          status: "completed",
          agent: "single_agent",
          terminal: [],
          substeps: [{ id: "todo_1_step_1", content: "读取原文", status: "completed" }],
        },
        {
          id: "todo_2",
          content: "写成 Markdown",
          status: "running",
          agent: "single_agent",
          terminal: [],
        },
      ],
    );
    expect(items.map((i) => i.content)).toEqual(["抓取文章", "写成 Markdown"]);
    expect(items[0].substeps.map((s) => s.content)).toEqual(["读取原文"]);
    expect(items[1].status).toBe("running");
  });

  it("shows a completed parent with all unfinished child indicators completed", () => {
    const items = buildProgressItems([{
      id: "todo_1", content: "整理答复", status: "completed", terminal: [],
      substeps: [
        { id: "a", content: "梳理要点", status: "completed" },
        { id: "b", content: "标注来源", status: "running" },
      ],
    }]);
    expect(items[0].substeps.map((step) => step.status)).toEqual(["completed", "completed"]);
  });

  it("keeps tool calls in execution details under the active step", () => {
    const tasks = [{ id: "todo_1", content: "检索材料", status: "running" as const }];
    const trace = [
      { id: "1", type: "todo_state", payload: { todos: [{ id: "todo_1", status: "in_progress" }] } },
      { id: "2", type: "tool.start", payload: { agent_id: "single_agent", tool: "web_search", call_id: "c1" } },
      { id: "3", type: "tool.result", payload: { agent_id: "single_agent", tool: "web_search", call_id: "c1" } },
    ];
    expect(buildStepExecutionDetails(trace, tasks).todo_1).toHaveLength(1);
    expect(buildStepExecutionDetails(trace, tasks).todo_1[0].done).toBe(true);
  });

  it("uses explicit subtask ids for parallel workforce tools", () => {
    const tasks = [
      { id: "task_a", content: "检索", status: "running" as const },
      { id: "task_b", content: "整理", status: "running" as const },
    ];
    const trace = [
      { id: "1", type: "tool.result", payload: { agent_id: "browser_agent", sub_task_id: "task_a", tool: "web_search", call_id: "a" } },
      { id: "2", type: "tool.result", payload: { agent_id: "document_agent", sub_task_id: "task_b", tool: "fs_write", call_id: "b" } },
    ];
    const details = buildStepExecutionDetails(trace, tasks);
    expect(details.task_a.map((row) => row.id)).toEqual(["a"]);
    expect(details.task_b.map((row) => row.id)).toEqual(["b"]);
  });
});

describe("workforce plan progress", () => {
  it("keeps a confirmed custom-id global step while syncing its substeps", () => {
    const store = createWorkforceStore();
    store.getState().handleWorkforceEvent("to_sub_tasks", {
      task_id: "run-1",
      subtasks: [{ id: "research", content: "检索资料", assignee: "browser_agent", substeps: [{ content: "查找官网" }] }],
    });
    store.getState().handleWorkforceEvent("todo_state", {
      todos: [{ id: "research", content: "检索资料", status: "completed", substeps: [{ id: "research_step_1", content: "查找官网", status: "completed" }] }],
    });
    expect(store.getState().sessionMode).toBe("workforce");
    expect(store.getState().taskInfo[0].id).toBe("research");
    expect(store.getState().taskInfo[0].substeps?.[0].status).toBe("completed");
  });

  it("updates only the reported child step during workforce execution", () => {
    const store = createWorkforceStore();
    store.getState().handleWorkforceEvent("to_sub_tasks", {
      task_id: "run-2",
      subtasks: [{ id: "research", content: "检索资料", assignee: "browser_agent", substeps: [{ content: "查找官网" }, { content: "核对来源" }] }],
    });
    store.getState().handleWorkforceEvent("substep_state", {
      parent_id: "research", substep_id: "research_step_1", status: "completed",
    });
    expect(store.getState().taskInfo[0].substeps?.map((step) => step.status)).toEqual(["completed", "waiting"]);
  });

  it("completes open child steps when todo_state completes a single-agent parent", () => {
    const store = createWorkforceStore();
    store.getState().handleWorkforceEvent("todo_state", {
      todos: [{ id: "todo_1", content: "整理答复", status: "completed", substeps: [
        { id: "todo_1_step_1", content: "梳理要点", status: "completed" },
        { id: "todo_1_step_2", content: "标注来源", status: "in_progress" },
      ] }],
    });
    expect(store.getState().taskInfo[0].substeps?.map((step) => step.status)).toEqual(["completed", "completed"]);
  });

  it("keeps completed child steps complete after a late substep event", () => {
    const store = createWorkforceStore();
    store.getState().seedPlan([{ id: "research", content: "检索资料", status: "completed", terminal: [],
      substeps: [{ id: "research_step_1", content: "查找官网", status: "waiting" }] }]);
    store.getState().handleWorkforceEvent("substep_state", {
      parent_id: "research", substep_id: "research_step_1", status: "in_progress",
    });
    expect(store.getState().taskInfo[0].substeps?.[0].status).toBe("completed");
  });

  it("completes remaining children when task_state finishes a workforce step", () => {
    const store = createWorkforceStore();
    store.getState().seedPlan([{ id: "research", content: "检索资料", status: "running", terminal: [],
      substeps: [
        { id: "research_step_1", content: "查找官网", status: "completed" },
        { id: "research_step_2", content: "核对来源", status: "running" },
      ] }]);
    store.getState().handleWorkforceEvent("task_state", { sub_task_id: "research", status: "completed" });
    expect(store.getState().taskInfo[0].substeps?.map((step) => step.status)).toEqual(["completed", "completed"]);
  });
});
