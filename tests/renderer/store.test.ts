import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { subscribeSSE } from "../../renderer/src/api/sse";
import { useSessionStore } from "../../renderer/src/store/session";

function resetStore() {
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
    useSessionStore.getState().handleEvent({ type: "graph.end", payload: { status: "ok" } });

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

  it("step.delta after a confirm starts a new assistant message", () => {
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
    expect(answers.at(-1)?.content).toContain("两个方案的主要风险如下");
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
