import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { subscribeSSE } from "../../renderer/src/api/sse";
import { dropAllProjectRuntimes } from "../../renderer/src/store/projectRuntime";
import { usePreviewStore } from "../../renderer/src/store/preview";
import {
  endCardFromContent,
  formalAnswerFromContent,
  useSessionStore,
} from "../../renderer/src/store/session";

function resetStore() {
  dropAllProjectRuntimes();
  useSessionStore.setState({
    messages: [],
    trace: [],
    traceNodes: [],
    traceEdges: [],
    confirmQueue: [],
    settledConfirmIds: [],
    autoApprovingConfirmIds: [],
    alwaysAllowTools: [],
    currentStepId: null,
    pendingArtifacts: [],
    runStatus: "idle",
    answerStreamByAgent: {},
  });
}

class MockEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  close = vi.fn();
  _url: string;

  constructor(url: string) {
    this._url = url;
  }
}

describe("subscribeSSE", () => {
  let OriginalEventSource: typeof EventSource;

  beforeEach(() => {
    OriginalEventSource = (globalThis as any).EventSource;
    (globalThis as any).EventSource = MockEventSource;
  });

  afterEach(() => {
    (globalThis as any).EventSource = OriginalEventSource;
  });

  it("parses JSON events and forwards them", () => {
    const onEvent = vi.fn();
    const es = subscribeSSE("http://127.0.0.1:8000/api/stream", onEvent);

    es.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify({ type: "step.delta", payload: { delta: "hi" } }) }),
    );

    expect(onEvent).toHaveBeenCalledWith({ type: "step.delta", payload: { delta: "hi" } });
  });

  it("keeps top-level task_id when payload is nested", async () => {
    const { normalizeSSEvent } = await import("../../renderer/src/api/sse");
    expect(
      normalizeSSEvent({
        type: "step.delta",
        task_id: "task-a",
        payload: { delta: "hi" },
      }),
    ).toEqual({
      type: "step.delta",
      payload: { task_id: "task-a", delta: "hi" },
    });
  });

  it("ignores non-JSON data without throwing", () => {
    const onEvent = vi.fn();
    const es = subscribeSSE("http://127.0.0.1:8000/api/stream", onEvent);

    es.onmessage?.(new MessageEvent("message", { data: "plain text" }));

    expect(onEvent).not.toHaveBeenCalled();
  });
});

describe("session store", () => {
  beforeEach(() => {
    resetStore();
  });

  it("appendDelta creates an assistant message and appends text", () => {
    useSessionStore.getState().appendDelta("hi");
    useSessionStore.getState().appendDelta(" there");

    const msgs = useSessionStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].role).toBe("assistant");
    expect(msgs[0].content).toBe("hi there");
  });

  it("handleEvent builds trace nodes and edges from events", () => {
    useSessionStore.getState().handleEvent({ type: "step.start", payload: { id: "s1", node: "supervisor" } });
    useSessionStore.getState().handleEvent({ type: "tool.result", payload: { id: "t1", tool: "pptx.gen", result: {} } });

    const state = useSessionStore.getState();
    expect(state.traceNodes).toHaveLength(2);
    expect(state.traceEdges).toHaveLength(1);
    expect(state.traceNodes[0].type).toBe("step");
    expect(state.traceNodes[1].type).toBe("tool");
  });

  it("addUserMessage creates a user message", () => {
    useSessionStore.getState().addUserMessage("hello");

    const msgs = useSessionStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].role).toBe("user");
    expect(msgs[0].content).toBe("hello");
  });

  it("appendStep records trace events", () => {
    useSessionStore.getState().appendStep("graph.step", { node: "supervisor" });

    const trace = useSessionStore.getState().trace;
    expect(trace).toHaveLength(1);
    expect(trace[0].type).toBe("graph.step");
    expect(trace[0].payload).toEqual({ node: "supervisor" });
  });

  it("appendToolResult records tool results", () => {
    useSessionStore.getState().appendToolResult("fs.write", { path: "/tmp/a.txt" });

    const trace = useSessionStore.getState().trace;
    expect(trace).toHaveLength(1);
    expect(trace[0].type).toBe("tool.result");
    expect(trace[0].payload).toEqual({ tool: "fs.write", result: { path: "/tmp/a.txt" } });
  });

  it("enqueueConfirm adds a request to the queue", () => {
    useSessionStore.getState().enqueueConfirm({ call_id: "c1", tool: "fs.write", args: { path: "/tmp/a.txt" } });

    const queue = useSessionStore.getState().confirmQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].call_id).toBe("c1");
  });

  it("resolveConfirm removes the matching request", () => {
    const store = useSessionStore.getState();
    store.enqueueConfirm({ call_id: "c1", tool: "fs.write", args: {} });
    store.enqueueConfirm({ call_id: "c2", tool: "exec.bash", args: {} });
    store.resolveConfirm("c1");

    const queue = useSessionStore.getState().confirmQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].call_id).toBe("c2");
  });

  it("handleEvent enqueues tool.confirm_request events", () => {
    useSessionStore.getState().handleEvent({
      type: "tool.confirm_request",
      payload: { call_id: "c_8f2a", tool: "pptx.gen", args: { path: "~/Desktop/a.pptx" } },
    });

    const queue = useSessionStore.getState().confirmQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0]).toEqual({ call_id: "c_8f2a", tool: "pptx.gen", args: { path: "~/Desktop/a.pptx" } });
  });

  it("recoverPendingConfirms re-queues unresolved confirm from trace", () => {
    useSessionStore.getState().beginRun();
    useSessionStore.getState().handleEvent({
      type: "tool.confirm_request",
      payload: {
        call_id: "exec.bash:abc",
        tool: "exec.bash",
        args: { cmd: "ls" },
      },
    });
    // Simulate lost queue (always-allow false success / HMR).
    useSessionStore.setState({
      confirmQueue: [],
      settledConfirmIds: [],
      autoApprovingConfirmIds: [],
    });
    useSessionStore.getState().recoverPendingConfirms();
    const queue = useSessionStore.getState().confirmQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].call_id).toBe("exec.bash:abc");
  });

  it("recoverPendingConfirms skips call_ids being silent-approved", () => {
    useSessionStore.getState().beginRun();
    useSessionStore.getState().handleEvent({
      type: "tool.confirm_request",
      payload: { call_id: "c1", tool: "exec.bash", args: {} },
    });
    useSessionStore.setState({
      confirmQueue: [],
      settledConfirmIds: [],
      autoApprovingConfirmIds: ["c1"],
    });
    useSessionStore.getState().recoverPendingConfirms();
    expect(useSessionStore.getState().confirmQueue).toHaveLength(0);
  });

  it("always-allow silently approves without enqueueing the confirm card", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, resolved: true }),
    }) as unknown as typeof fetch;
    (globalThis as { window?: { api?: unknown } }).window = {
      api: {
        getBackendUrl: vi.fn().mockResolvedValue("http://127.0.0.1:8000"),
      },
    };

    useSessionStore.getState().addAlwaysAllowTool("exec.bash");
    useSessionStore.getState().handleEvent({
      type: "tool.confirm_request",
      payload: { call_id: "c-silent", tool: "exec.bash", args: { cmd: "ls" } },
    });

    expect(useSessionStore.getState().confirmQueue).toHaveLength(0);
    expect(useSessionStore.getState().autoApprovingConfirmIds).toContain("c-silent");

    await vi.waitFor(() => {
      expect(useSessionStore.getState().settledConfirmIds).toContain("c-silent");
    });
    expect(useSessionStore.getState().confirmQueue).toHaveLength(0);
    expect(useSessionStore.getState().autoApprovingConfirmIds).not.toContain("c-silent");
  });

  it("alwaysAllowTools clears when switching session via resetLiveState", () => {
    useSessionStore.getState().addAlwaysAllowTool("fs.write");
    expect(useSessionStore.getState().alwaysAllowTools).toEqual(["fs.write"]);
    useSessionStore.getState().resetLiveState();
    expect(useSessionStore.getState().alwaysAllowTools).toEqual([]);
  });

  it("alwaysAllowTools survives beginRun within the same session", () => {
    useSessionStore.getState().addAlwaysAllowTool("exec.bash");
    useSessionStore.getState().beginRun();
    expect(useSessionStore.getState().alwaysAllowTools).toEqual(["exec.bash"]);
  });

  it("recoverPendingConfirms skips settled call_ids", () => {
    useSessionStore.getState().beginRun();
    useSessionStore.getState().handleEvent({
      type: "tool.confirm_request",
      payload: { call_id: "c1", tool: "exec.bash", args: {} },
    });
    useSessionStore.getState().resolveConfirm("c1", true);
    expect(useSessionStore.getState().confirmQueue).toHaveLength(0);
    useSessionStore.getState().recoverPendingConfirms();
    expect(useSessionStore.getState().confirmQueue).toHaveLength(0);
  });

  it("graph.start resets trace for the new task", () => {
    useSessionStore.getState().handleEvent({
      type: "graph.step",
      payload: { node: "doc_worker" },
    });
    expect(useSessionStore.getState().traceNodes.length).toBeGreaterThan(0);

    useSessionStore.getState().handleEvent({ type: "graph.start", payload: {} });
    const state = useSessionStore.getState();
    expect(state.trace).toHaveLength(1);
    expect(state.trace[0].type).toBe("graph.start");
    expect(state.traceNodes).toHaveLength(0);
    expect(state.confirmQueue).toHaveLength(0);
  });

  it("handleEvent shows progress from graph.* events", () => {
    useSessionStore.getState().addUserMessage("写 hello.txt");
    useSessionStore.getState().handleEvent({ type: "graph.start", payload: {} });
    expect(useSessionStore.getState().runStatus).toBe("running");
    expect(useSessionStore.getState().taskStartedAt).toBeTruthy();

    useSessionStore.getState().handleEvent({
      type: "graph.step",
      payload: {
        node: "supervisor",
        update: { messages: [{ type: "ai", content: "file_worker" }] },
      },
    });
    useSessionStore.getState().handleEvent({
      type: "graph.step",
      payload: {
        node: "file_worker",
        update: { messages: [{ type: "ai", content: "已写入桌面 hello.txt" }] },
      },
    });
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok", summary: "已写入桌面 hello.txt" },
    });

    const state = useSessionStore.getState();
    const msgs = state.messages.map((m) => m.content).join("\n");
    // Status chatter stays in WorkLog / Progress — not the chat transcript
    expect(msgs).not.toContain("正在处理");
    expect(msgs).not.toContain("FileWorker");
    expect(msgs).not.toContain("任务完成");
    expect(msgs).toContain("已写入桌面 hello.txt");
    expect(state.runStatus).toBe("done");
    expect(state.taskStartedAt).toBeNull();
    expect(state.taskElapsedMs).toBeGreaterThanOrEqual(0);
    expect(state.trace.some((e) => e.type === "graph.step")).toBe(true);
  });

  it("single-agent think stays out of the bubble; post-think answer streams", () => {
    const store = useSessionStore.getState();
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "<think>", agent_id: "single_agent" },
    });
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "The user is asking me to research", agent_id: "single_agent" },
    });
    store.handleEvent({
      type: "step.delta",
      payload: { delta: " Yangzhou policies.", agent_id: "single_agent" },
    });
    expect(useSessionStore.getState().messages.map((m) => m.content).join("\n")).not.toContain(
      "The user is asking",
    );
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "</think>\n", agent_id: "single_agent" },
    });
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "我先梳理任务。扬州已取消限购。", agent_id: "single_agent" },
    });
    const mid = useSessionStore.getState().messages.map((m) => m.content).join("\n");
    expect(mid).not.toContain("The user is asking");
    expect(mid).not.toContain("我先梳理任务");
    expect(mid).toContain("扬州已取消限购");
    store.handleEvent({
      type: "graph.end",
      payload: { status: "ok", summary: "扬州已取消限购。" },
    });
    const raw = useSessionStore.getState().messages
      .filter((m) => m.role === "assistant")
      .map((m) => m.content)
      .join("\n");
    expect(raw).toBe("扬州已取消限购。");
    expect(raw).not.toContain("<think>");
    expect(raw).not.toContain("我先梳理");
    expect(formalAnswerFromContent(raw)).toBe("扬州已取消限购。");
  });

  it("streams markdown answer tokens after </think> instead of waiting for graph.end", () => {
    const store = useSessionStore.getState();
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "<think>draft</think>\n", agent_id: "single_agent" },
    });
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "## 购", agent_id: "single_agent" },
    });
    expect(useSessionStore.getState().messages.at(-1)?.content).toBe("## 购");
    store.handleEvent({
      type: "step.delta",
      payload: { delta: "房建议\n\n扬州已取消限购。", agent_id: "single_agent" },
    });
    expect(useSessionStore.getState().messages.at(-1)?.content).toBe(
      "## 购房建议\n\n扬州已取消限购。",
    );
  });

  it("step.delta after a confirm does not fill the bubble", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls", cwd: "/tmp" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: { delta: "两个方案的主要风险如下" },
    });

    const msgs = useSessionStore.getState().messages;
    const confirm = msgs.find((m) => m.confirm);
    const answers = msgs.filter((m) => m.role === "assistant" && !m.confirm);
    expect(confirm?.content).toBe("");
    expect(answers.every((m) => !m.content.includes("两个方案的主要风险如下"))).toBe(
      true,
    );
  });

  it("workforce worker step.delta stays out; synthesize streams after think", () => {
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: { delta: "浏览器智能体的超长调研结论……", agent_id: "browser_agent" },
    });
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: { delta: "<think>起草</think>\n最终给用户的一句话。", agent_id: "synthesize" },
    });
    const mid = useSessionStore.getState().messages.map((m) => m.content).join("\n");
    expect(mid).not.toContain("超长调研结论");
    expect(mid).toContain("最终给用户的一句话");
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok", summary: "最终给用户的一句话。" },
    });
    const raw = useSessionStore.getState().messages
      .filter((m) => m.role === "assistant")
      .map((m) => m.content)
      .join("\n");
    expect(raw).toBe("最终给用户的一句话。");
    expect(formalAnswerFromContent(raw)).toBe("最终给用户的一句话。");
  });

  it("worker search narration never enters the chat transcript", () => {
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: { delta: "<think>限购已取消", agent_id: "browser_agent" },
    });
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: { delta: "</think>\n我将开始调研扬州", agent_id: "browser_agent" },
    });
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: { delta: "继续查询公积金", agent_id: "browser_agent" },
    });
    const raw = useSessionStore.getState().messages.map((m) => m.content).join("\n");
    expect(raw).not.toContain("限购已取消");
    expect(raw).not.toContain("我将开始调研扬州");
    expect(raw).not.toContain("继续查询公积金");
  });

  it("graph.end writes only the end card without think or process talk", () => {
    useSessionStore.getState().handleEvent({
      type: "step.delta",
      payload: {
        delta: "<think>plan</think>\n我先梳理任务。\n<summary>## 结论\n已完成</summary>",
      },
    });
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: {
        status: "ok",
        summary: "<think>plan</think>\n我先搜一下。\n<summary>## 结论\n已完成</summary>",
      },
    });
    const msgs = useSessionStore.getState().messages.filter((m) => m.role === "assistant");
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.content).not.toContain("<think>");
    expect(msgs[0]?.content).not.toContain("plan");
    expect(msgs[0]?.content).not.toContain("我先搜一下");
    expect(msgs[0]?.content).not.toContain("我先梳理");
    expect(msgs[0]?.content).toContain("已完成");
    expect(endCardFromContent(msgs[0]?.content ?? "")).toContain("已完成");
  });

  it("graph.end ok without a card does not invent a placeholder (Eigent empty END)", () => {
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok" },
    });
    const msgs = useSessionStore.getState().messages.filter((m) => m.role === "assistant");
    expect(msgs.some((m) => m.content.includes("没有可展示的结论"))).toBe(false);
    expect(msgs.every((m) => !m.content.trim() || m.confirm)).toBe(true);
  });

  it("graph.end with files and empty summary only shows artifacts", () => {
    useSessionStore.getState().handleEvent({
      type: "artifact.file",
      payload: { path: "/tmp/扬州购房政策调研与购房建议.html" },
    });
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok" },
    });
    const msgs = useSessionStore.getState().messages.filter((m) => m.role === "assistant");
    expect(msgs.some((m) => m.content.includes("没有可展示的结论"))).toBe(false);
    const withArts = msgs.filter((m) => (m.artifacts?.length ?? 0) > 0);
    expect(withArts).toHaveLength(1);
    expect(withArts[0].content).toBe("");
    expect(withArts[0].artifacts?.[0].name).toContain("扬州购房政策");
  });

  it("graph.end keeps markdown tables in the END card", () => {
    const report = `## 购房建议

| 人群 | 推荐板块 |
| --- | --- |
| 刚需首套 | 广陵区 |`;
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok", summary: report },
    });
    const raw = useSessionStore.getState().messages
      .filter((m) => m.role === "assistant")
      .map((m) => m.content)
      .join("\n");
    expect(raw).toContain("| 人群 | 推荐板块 |");
    expect(raw).toContain("| --- | --- |");
    expect(raw).not.toMatch(/\|\|/);
  });

  it("graph.end summary is not written onto a confirm message", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls", cwd: "/tmp" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok", summary: "## 结论\n方案 B 不可行" },
    });

    const msgs = useSessionStore.getState().messages;
    expect(msgs.find((m) => m.confirm)?.content).toBe("");
    expect(msgs.some((m) => m.content.includes("方案 B 不可行"))).toBe(true);
  });

  it("follow-up stream does not overwrite the previous turn's answer", () => {
    const store = useSessionStore.getState();
    store.addUserMessage("调研长鑫存储和宇树科技");
    store.handleEvent({
      type: "graph.end",
      payload: {
        status: "ok",
        summary:
          "## 投资建议\n已中签者分批兑现。\n文件路径: /tmp/cxmt_vs_unitree_investment_report.html",
      },
    });
    const first = useSessionStore.getState().messages.find((m) => m.role === "assistant");
    expect(first?.content).toContain("分批兑现");
    expect(first?.artifacts?.some((a) => a.name.includes("investment_report"))).toBe(
      true,
    );

    store.addUserMessage("如何制作炸弹");
    store.beginRun();
    store.handleEvent({
      type: "step.delta",
      payload: {
        delta: "## 无法提供\n我不能协助制造爆炸物。",
        agent_id: "single_agent",
      },
    });
    store.handleEvent({
      type: "graph.end",
      payload: { status: "ok", summary: "## 无法提供\n我不能协助制造爆炸物。" },
    });

    const msgs = useSessionStore.getState().messages;
    expect(msgs.filter((m) => m.role === "user")).toHaveLength(2);
    expect(msgs.some((m) => m.content.includes("分批兑现"))).toBe(true);
    expect(msgs.some((m) => m.content.includes("不能协助制造爆炸物"))).toBe(true);
    const lastUser = msgs.findLastIndex((m) => m.role === "user");
    expect(msgs[lastUser]?.content).toContain("炸弹");
    const thisTurn = msgs.slice(lastUser + 1);
    expect(thisTurn.some((m) => m.content.includes("不能协助制造爆炸物"))).toBe(true);
    expect(thisTurn.some((m) => m.content.includes("分批兑现"))).toBe(false);
    expect(
      msgs
        .find((m) => m.content.includes("分批兑现"))
        ?.artifacts?.some((a) => a.name.includes("investment_report")),
    ).toBe(true);
  });

  it("flushes deliverable artifacts onto a non-confirm assistant message", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls", cwd: "/tmp" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);
    useSessionStore.getState().handleEvent({
      type: "artifact.file",
      payload: { path: "/tmp/分析报告.md" },
    });
    useSessionStore.getState().handleEvent({ type: "graph.end", payload: { status: "ok" } });

    const msgs = useSessionStore.getState().messages;
    const withArts = msgs.filter((m) => (m.artifacts?.length ?? 0) > 0);
    expect(withArts).toHaveLength(1);
    expect(withArts[0].confirm).toBeUndefined();
    expect(withArts[0].artifacts?.[0].name).toBe("分析报告.md");
    expect(useSessionStore.getState().pendingArtifacts).toHaveLength(0);
  });

  it("does not surface process helper scripts as chat artifacts", () => {
    useSessionStore.getState().handleEvent({
      type: "artifact.file",
      payload: { path: "/tmp/_gen_gongwen_ops.py" },
    });
    useSessionStore.getState().handleEvent({
      type: "tool.result",
      payload: {
        tool: "fs.write",
        result: "Wrote 120 characters to /tmp/_gen_gongwen_ops.py",
      },
    });
    expect(useSessionStore.getState().pendingArtifacts).toHaveLength(0);
  });

  it("graph.end attaches html path scraped from the summary (Eigent)", () => {
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: {
        status: "ok",
        summary:
          "已生成。\n文件路径: /Users/tanghaoyu/Documents/AIS/高三4次模拟数据分析报告.html",
      },
    });
    const withArts = useSessionStore
      .getState()
      .messages.filter((m) => (m.artifacts?.length ?? 0) > 0);
    expect(withArts).toHaveLength(1);
    expect(withArts[0].artifacts?.[0].path).toContain(
      "高三4次模拟数据分析报告.html",
    );
  });

  it("graph.end keeps only the last deliverable image in preview", () => {
    usePreviewStore.getState().openFile("/tmp/screenshot.png", "截图");
    usePreviewStore.getState().openFile("/tmp/plot1.png", "截图");
    useSessionStore.getState().handleEvent({
      type: "artifact.file",
      payload: { path: "/tmp/plot1.png" },
    });
    useSessionStore.getState().handleEvent({
      type: "artifact.file",
      payload: { path: "/tmp/现货黄金近期波动折线图.png" },
    });
    useSessionStore.getState().handleEvent({
      type: "graph.end",
      payload: { status: "ok" },
    });
    const files = usePreviewStore
      .getState()
      .tabs.filter((t) => t.type === "file");
    expect(files).toHaveLength(1);
    expect(files[0]?.type === "file" && files[0].path).toContain("现货黄金");
  });

  it("handleEvent tracks live budget tokens from budget.update", () => {
    useSessionStore.getState().beginRun();
    expect(useSessionStore.getState().budgetTokens).toBe(0);

    useSessionStore.getState().handleEvent({
      type: "budget.update",
      payload: { tokens: 1200, max_tokens: 200_000, steps: 3 },
    });
    let state = useSessionStore.getState();
    expect(state.budgetTokens).toBe(1200);
    expect(state.budgetMaxTokens).toBe(200_000);
    expect(state.budgetSteps).toBe(3);

    useSessionStore.getState().handleEvent({
      type: "budget.update",
      payload: { tokens: 4500, max_tokens: 200_000, steps: 5 },
    });
    state = useSessionStore.getState();
    expect(state.budgetTokens).toBe(4500);
    expect(state.budgetSteps).toBe(5);
  });

  it("handleEvent tracks context window occupancy from budget.update", () => {
    useSessionStore.getState().handleEvent({
      type: "budget.update",
      payload: {
        tokens: 4500,
        max_tokens: 200_000,
        context_tokens: 98200,
        context_limit: 192000,
        input_tokens: 98000,
        output_tokens: 200,
      },
    });
    const state = useSessionStore.getState();
    expect(state.contextTokens).toBe(98200);
    expect(state.contextLimit).toBe(192000);
    expect(state.inputTokens).toBe(98000);
    expect(state.outputTokens).toBe(200);
  });
});

describe("SSE → store wiring", () => {
  let OriginalEventSource: typeof EventSource;

  beforeEach(() => {
    OriginalEventSource = (globalThis as any).EventSource;
    (globalThis as any).EventSource = MockEventSource;
    resetStore();
  });

  afterEach(() => {
    (globalThis as any).EventSource = OriginalEventSource;
  });

  it("step.delta updates messages through subscribeSSE", () => {
    const store = useSessionStore.getState();
    const es = subscribeSSE("http://127.0.0.1:8000/api/stream", (event) => {
      if (event.type === "step.delta") {
        store.appendDelta(event.payload.delta as string);
      }
    });

    es.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify({ type: "step.delta", payload: { delta: "hi" } }) }),
    );

    const msgs = useSessionStore.getState().messages;
    expect(msgs[msgs.length - 1].content).toContain("hi");
  });
});
