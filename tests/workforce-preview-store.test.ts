/**
 * Phase0 store smoke: fake SSE events drive workforce + preview.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { usePreviewStore } from "../renderer/src/store/preview";
import { useWorkforceStore } from "../renderer/src/store/workforce";
import { SessionMode } from "../renderer/src/types/workforce";

describe("workforce + preview stores", () => {
  beforeEach(() => {
    useWorkforceStore.getState().reset();
    usePreviewStore.getState().reset();
    useWorkforceStore.getState().setSessionMode(SessionMode.WORKFORCE);
  });

  it("activates agent cards from agent.* events", () => {
    const wf = useWorkforceStore.getState();
    wf.handleWorkforceEvent("agent.create", {
      agent_id: "developer_agent",
      name: "Developer Agent",
      agent_type: "developer_agent",
    });
    wf.handleWorkforceEvent("agent.activate", { agent_id: "developer_agent" });
    wf.handleWorkforceEvent("agent.assign", {
      agent_id: "developer_agent",
      assign_id: "t1",
      content: "write",
      status: "running",
    });
    const agent = useWorkforceStore
      .getState()
      .taskAssigning.find((a) => a.agent_id === "developer_agent");
    expect(agent?.status).toBe("running");
    expect(useWorkforceStore.getState().taskRunning.length).toBe(1);
  });

  it("loads Progress plan from to_sub_tasks (Eigent workforce)", () => {
    useWorkforceStore.getState().handleWorkforceEvent("to_sub_tasks", {
      task_id: "tid-1",
      subtasks: [
        {
          id: "task_1",
          content: "解读附件并提炼建议",
          assignee: "browser_agent",
          dependencies: [],
        },
        {
          id: "task_2",
          content: "整理建设性修改意见",
          assignee: "document_agent",
          dependencies: ["task_1"],
        },
      ],
    });
    const pending = useWorkforceStore.getState().pendingPlan;
    expect(pending?.taskId).toBe("tid-1");
    expect(pending?.subtasks).toHaveLength(2);
    const info = useWorkforceStore.getState().taskInfo;
    expect(info).toHaveLength(2);
    expect(info[0].content).toBe("解读附件并提炼建议");
    expect(useWorkforceStore.getState().sessionMode).toBe(SessionMode.WORKFORCE);
  });

  it("workforce todo_state syncs status without rewriting plan content", () => {
    const wf = useWorkforceStore.getState();
    wf.handleWorkforceEvent("to_sub_tasks", {
      task_id: "tid-2",
      subtasks: [
        { id: "task_1", content: "读文档", assignee: "browser_agent", dependencies: [] },
        { id: "task_2", content: "写建议", assignee: "document_agent", dependencies: ["task_1"] },
      ],
    });
    wf.handleWorkforceEvent("todo_state", {
      agent_id: "coordinator",
      todos: [
        {
          id: "task_1",
          content: "读文档",
          active_form: "正在执行：读文档",
          status: "completed",
        },
        {
          id: "task_2",
          content: "写建议",
          active_form: "正在执行：写建议",
          status: "in_progress",
        },
      ],
    });
    const info = useWorkforceStore.getState().taskInfo;
    expect(info[0].content).toBe("读文档");
    expect(info[0].status).toBe("completed");
    expect(info[1].content).toBe("写建议");
    expect(info[1].status).toBe("running");
  });

  it("workforce ignores foreign todo_write rewrite", () => {
    const wf = useWorkforceStore.getState();
    wf.handleWorkforceEvent("to_sub_tasks", {
      task_id: "tid-3",
      subtasks: [
        { id: "task_1", content: "用户确认的计划", assignee: "browser_agent", dependencies: [] },
      ],
    });
    wf.handleWorkforceEvent("todo_state", {
      agent_id: "browser_agent",
      todos: [
        {
          id: "todo_1",
          content: "Extracting key arguments",
          active_form: "Extracting key arguments",
          status: "in_progress",
        },
      ],
    });
    const info = useWorkforceStore.getState().taskInfo;
    expect(info).toHaveLength(1);
    expect(info[0].content).toBe("用户确认的计划");
  });

  it("loads Progress plan from todo_state", () => {
    useWorkforceStore.getState().setSessionMode(SessionMode.SINGLE_AGENT);
    useWorkforceStore.getState().handleWorkforceEvent("todo_state", {
      agent_id: "single_agent",
      todos: [
        {
          id: "todo_1",
          content: "理解用户需求与交付目标",
          active_form: "正在理解需求",
          status: "in_progress",
        },
        {
          id: "todo_2",
          content: "检索相关资料与政策流程",
          active_form: "正在检索资料",
          status: "pending",
        },
      ],
    });
    const info = useWorkforceStore.getState().taskInfo;
    expect(info).toHaveLength(2);
    expect(info[0].status).toBe("running");
    expect(info[0].content).toContain("正在理解需求");
    expect(info[1].status).toBe("waiting");
  });

  it("opens preview tabs from preview.open / screenshot", () => {
    const pv = usePreviewStore.getState();
    pv.handlePreviewEvent("preview.open", { kind: "browser", url: "https://example.com" });
    expect(usePreviewStore.getState().open).toBe(true);
    expect(usePreviewStore.getState().tabs.some((t) => t.type === "browser")).toBe(true);
    pv.handlePreviewEvent("artifact.screenshot", { path: "/tmp/shot.png" });
    expect(usePreviewStore.getState().tabs.some((t) => t.type === "file")).toBe(true);
  });

  it("opens terminal with assign_id (not session task_id) and keeps output", () => {
    const wf = useWorkforceStore.getState();
    const pv = usePreviewStore.getState();
    const sessionId = "run-abc";
    const assignId = `${sessionId}:developer_agent`;

    wf.handleWorkforceEvent("agent.create", {
      agent_id: "developer_agent",
      name: "Developer Agent",
      agent_type: "developer_agent",
    });
    wf.handleWorkforceEvent("agent.activate", { agent_id: "developer_agent" });
    wf.handleWorkforceEvent("agent.assign", {
      agent_id: "developer_agent",
      assign_id: assignId,
      content: "run ls",
      status: "running",
    });
    wf.handleWorkforceEvent("agent.terminal", {
      agent_id: "developer_agent",
      assign_id: assignId,
      output: "total 0\n",
    });

    // Bug regression: payload.task_id is the session run id — must not be used as tab taskId.
    pv.handlePreviewEvent("preview.open", {
      kind: "terminal",
      task_id: sessionId,
      agent_id: "developer_agent",
      assign_id: assignId,
    });

    const tab = usePreviewStore.getState().tabs.find((t) => t.type === "terminal");
    expect(tab?.type).toBe("terminal");
    if (tab?.type === "terminal") {
      expect(tab.agentId).toBe("developer_agent");
      expect(tab.taskId).toBe(assignId);
      expect(tab.taskId).not.toBe(sessionId);
    }

    const agent = useWorkforceStore
      .getState()
      .taskAssigning.find((a) => a.agent_id === "developer_agent");
    expect(agent?.tasks[0]?.terminal).toEqual(["total 0\n"]);
  });

  it("appendTerminal falls back when assign_id mismatches task id", () => {
    const wf = useWorkforceStore.getState();
    wf.handleWorkforceEvent("agent.activate", { agent_id: "developer_agent" });
    wf.handleWorkforceEvent("agent.assign", {
      agent_id: "developer_agent",
      assign_id: "task_1",
      content: "run",
      status: "running",
    });
    wf.handleWorkforceEvent("agent.terminal", {
      agent_id: "developer_agent",
      assign_id: "run-xyz:developer_agent",
      output: "$ ls\nok\n",
    });
    const agent = useWorkforceStore
      .getState()
      .taskAssigning.find((a) => a.agent_id === "developer_agent");
    expect(agent?.tasks[0]?.id).toBe("task_1");
    expect(agent?.tasks[0]?.terminal).toEqual(["$ ls\nok\n"]);
  });
});
