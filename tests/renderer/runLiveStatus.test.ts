/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import { deriveLiveActivity } from "../../renderer/src/lib/runLiveStatus";
import type { TraceEvent } from "../../renderer/src/store/session";

describe("deriveLiveActivity", () => {
  it("prefers an in-flight tool over thinking copy", () => {
    const trace: TraceEvent[] = [
      {
        id: "1",
        type: "tool.start",
        payload: {
          tool: "web_search",
          call_id: "c1",
          preview: "扬州 限购",
          timestamp: "2026-08-21T12:00:00.000Z",
        },
      },
    ];
    const out = deriveLiveActivity({
      trace,
      taskInfo: [],
      taskRunning: [],
      confirmCount: 0,
      pendingArtifactCount: 0,
      thinkingSubject: "正在生成回答",
    });
    expect(out.label).toContain("检索网页");
    expect(out.label).toContain("扬州 限购");
    expect(out.phase).toBe("工具执行中");
  });

  it("shows composing copy while the answer is streaming", () => {
    const out = deriveLiveActivity({
      trace: [{ id: "1", type: "graph.start", payload: {} }],
      taskInfo: [],
      taskRunning: [],
      confirmCount: 0,
      pendingArtifactCount: 0,
      thinkingSubject: "正在生成回答",
    });
    expect(out.label).toBe("正在生成回答");
    expect(out.phase).toBe("正在组织回答");
  });

  it("does not throw on empty first-send state", () => {
    const out = deriveLiveActivity({
      trace: [],
      taskInfo: [],
      taskRunning: [],
      confirmCount: 0,
      pendingArtifactCount: 0,
      thinkingSubject: "开始分析任务",
    });
    expect(out.label).toBe("开始分析任务");
    expect(out.phase).toBe("正在启动任务");
  });

  it("waits on confirm before pending artifacts", () => {
    const out = deriveLiveActivity({
      trace: [
        {
          id: "1",
          type: "tool.confirm_request",
          payload: { tool: "fs.write", call_id: "c1" },
        },
      ],
      taskInfo: [],
      taskRunning: [],
      confirmCount: 1,
      pendingArtifactCount: 2,
    });
    expect(out.label).toContain("等待确认");
    expect(out.phase).toBe("等待你确认工具调用");
  });
});
