import { describe, expect, it } from "vitest";

import {
  formatWorkLogLine,
  humanizeAgent,
  humanizeAssignContent,
  humanizeTool,
} from "../../renderer/src/lib/processLabels";
import { buildWorkLogSteps } from "../../renderer/src/lib/progressFromTrace";

describe("processLabels", () => {
  it("localizes agent ids", () => {
    expect(humanizeAgent("browser_agent")).toBe("浏览器智能体");
    expect(humanizeAgent("coordinator")).toBe("任务协调");
  });

  it("localizes tools", () => {
    expect(humanizeTool("list_skills")).toBe("列出技能");
    expect(humanizeTool("fs.list")).toBe("列出文件");
    expect(humanizeTool("fs read")).toBe("读取文件");
    expect(humanizeTool("notes.create")).toBe("创建笔记");
    expect(humanizeTool("create note")).toBe("创建笔记");
    expect(humanizeTool("append note")).toBe("追加笔记");
    expect(humanizeTool("pptx.gen")).toBe("生成 PPT");
  });

  it("localizes Running/Finished assign lines", () => {
    expect(humanizeAssignContent("Running browser_agent")).toBe(
      "正在运行 · 浏览器智能体",
    );
    expect(humanizeAssignContent("Finished browser_agent")).toBe(
      "已完成 · 浏览器智能体",
    );
    expect(humanizeAssignContent("正在运行 · browser_agent")).toBe(
      "正在运行 · 浏览器智能体",
    );
    expect(humanizeAssignContent("调研运城景点")).toBe("调研运城景点");
  });

  it("formats work log lines without English agent ids", () => {
    expect(formatWorkLogLine("Running browser_agent", "browser_agent")).toBe(
      "正在运行 · 浏览器智能体",
    );
    expect(formatWorkLogLine("列出文件")).toBe("列出文件");
    expect(formatWorkLogLine("调研运城", "browser_agent")).toBe(
      "浏览器智能体 · 调研运城",
    );
  });

  it("buildWorkLogSteps matches single-agent: tools only, no worker rows", () => {
    const steps = buildWorkLogSteps(
      [
        {
          id: "1",
          type: "agent.assign",
          payload: {
            agent_id: "browser_agent",
            content: "Running browser_agent",
          },
        },
        {
          id: "2",
          type: "tool.result",
          payload: { tool: "list_skills" },
        },
        {
          id: "3",
          type: "graph.step",
          payload: { node: "coordinator" },
        },
      ],
      [],
    );
    const labels = steps.map((s) => formatWorkLogLine(s.label, s.detail));
    expect(labels.some((l) => /browser_agent|list_skills|Running /i.test(l))).toBe(
      false,
    );
    expect(labels).toContain("列出技能");
    expect(labels).not.toContain("正在运行 · 浏览器智能体");
    expect(labels).not.toContain("任务协调");
  });

  it("pairs tool.start with tool.result and keeps repeat calls", () => {
    const steps = buildWorkLogSteps(
      [
        {
          id: "s1",
          type: "tool.start",
          payload: {
            call_id: "c1",
            tool: "bash",
            preview: "officecli create a.docx",
            timestamp: "2026-08-19T15:00:00.000Z",
          },
        },
        {
          id: "s2",
          type: "tool.result",
          payload: { call_id: "c1", tool: "bash", preview: "officecli create a.docx" },
        },
        {
          id: "s3",
          type: "tool.start",
          payload: {
            call_id: "c2",
            tool: "bash",
            preview: "officecli add a.docx",
            timestamp: "2026-08-19T15:01:00.000Z",
          },
        },
      ],
      [],
    );
    const tools = steps.filter((s) => s.kind === "tool");
    expect(tools).toHaveLength(2);
    expect(tools[0].status).toBe("done");
    expect(tools[0].tool).toBe("bash");
    expect(tools[1].status).toBe("running");
    expect(tools[1].preview).toContain("officecli add");
  });
});
