/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatConfirmCard, { ChatConfirmRecord, ChatConfirmRecordGroup } from "../../renderer/src/components/chat/ChatConfirmCard";
import { useSessionStore } from "../../renderer/src/store/session";

const BACKEND_URL = "http://127.0.0.1:8000";

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
    runStatus: "running",
  });
}

describe("ChatConfirmCard", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    resetStore();
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, resolved: true }),
    }) as unknown as typeof fetch;
    window.api = {
      ...window.api,
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
    };
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("shows the confirm request details", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "pptx.gen",
      args: { path: "~/Desktop/a.pptx", slides: 5 },
    });

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msg.confirm!} />);

    // Title = humanizeTool("pptx.gen") = "生成 PPT"
    expect(screen.getByText("生成 PPT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "本次允许" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "本会话总是允许此工具" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeInTheDocument();
  });

  it("POSTs ok=true when allow is clicked", async () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "fs.write",
      args: { path: "~/Desktop/a.txt", content: "hi" },
    });

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msg.confirm!} />);

    await userEvent.click(screen.getByRole("button", { name: "本次允许" }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${BACKEND_URL}/api/tool/confirm/c1`,
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ok: true }),
        }),
      );
    });
  });

  it("POSTs ok=false when deny is clicked", async () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c2",
      tool: "exec.bash",
      args: { cmd: "ls -la", cwd: "/tmp" },
    });

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msg.confirm!} />);

    await userEvent.click(screen.getByRole("button", { name: "拒绝" }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${BACKEND_URL}/api/tool/confirm/c2`,
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ok: false }),
        }),
      );
    });
  });

  it("updates message confirm.status to allowed after responding", async () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "echo hi", cwd: "/tmp" },
    });

    const msgBefore = useSessionStore.getState().messages[0];
    expect(msgBefore.confirm?.status).toBe("pending");

    render(<ChatConfirmCard confirm={msgBefore.confirm!} />);

    await userEvent.click(screen.getByRole("button", { name: "本次允许" }));

    await waitFor(() => {
      const msgAfter = useSessionStore.getState().messages[0];
      expect(msgAfter.confirm?.status).toBe("allowed");
    });
  });

  it("updates message confirm.status to denied after rejecting", async () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "echo hi", cwd: "/tmp" },
    });

    const msgBefore = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msgBefore.confirm!} />);

    await userEvent.click(screen.getByRole("button", { name: "拒绝" }));

    await waitFor(() => {
      const msgAfter = useSessionStore.getState().messages[0];
      expect(msgAfter.confirm?.status).toBe("denied");
    });
  });

  it("renders exec.bash details with cmd and cwd", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls -la ./_scratch", cwd: "/tmp/work" },
    });

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msg.confirm!} />);

    expect(screen.getByText(/命令:/)).toBeInTheDocument();
    expect(screen.getByText(/ls -la \.\/_scratch/)).toBeInTheDocument();
    expect(screen.getByText(/工作目录:/)).toBeInTheDocument();
    expect(screen.getByText(/\/tmp\/work/)).toBeInTheDocument();
  });

  it("renders fs.write details with path and content summary", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "fs.write",
      args: { path: "~/Desktop/a.txt", content: "hello world" },
    });

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msg.confirm!} />);

    expect(screen.getByText(/路径:/)).toBeInTheDocument();
    expect(screen.getByText(/~\/Desktop\/a\.txt/)).toBeInTheDocument();
    expect(screen.getByText(/内容:/)).toBeInTheDocument();
    expect(screen.getByText(/hello world/)).toBeInTheDocument();
  });

  it("shows operation description below the title", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls", cwd: "/tmp" },
    });

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmCard confirm={msg.confirm!} />);

    expect(screen.getByText(/请求执行 Shell 命令/)).toBeInTheDocument();
  });
});

describe("ChatConfirmRecord", () => {
  beforeEach(() => {
    resetStore();
  });

  it("shows allowed record with operation summary", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls -la /tmp", cwd: "/home" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmRecord confirm={msg.confirm!} />);

    expect(screen.getByText("已允许")).toBeInTheDocument();
    expect(screen.getAllByText("执行命令").length).toBeGreaterThanOrEqual(1);
    // Operation summary stays in the folded details body
    expect(screen.getByText(/ls -la \/tmp/)).toBeInTheDocument();
    const record = screen.getByTestId("message-permission-record");
    expect(record.tagName).toBe("DETAILS");
    expect(record).not.toHaveAttribute("open");
  });

  it("shows denied record with operation summary", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c2",
      tool: "fs.write",
      args: { path: "/tmp/a.txt", content: "hello" },
    });
    useSessionStore.getState().resolveConfirm("c2", false);

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmRecord confirm={msg.confirm!} />);

    expect(screen.getByText("已拒绝")).toBeInTheDocument();
    expect(screen.getByText("编辑文件")).toBeInTheDocument();
    // Operation summary shows the file path
    expect(screen.getByText(/路径: \/tmp\/a\.txt/)).toBeInTheDocument();
    expect(screen.getByTestId("message-permission-record")).not.toHaveAttribute("open");
  });

  it("expands command details when the folded record is clicked", async () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls -la /tmp", cwd: "/home" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);

    const msg = useSessionStore.getState().messages[0];
    render(<ChatConfirmRecord confirm={msg.confirm!} />);

    const record = screen.getByTestId("message-permission-record");
    expect(record).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText("已允许"));
    expect(record).toHaveAttribute("open");
  });
});

describe("ChatConfirmRecordGroup", () => {
  beforeEach(() => {
    resetStore();
  });

  it("collapses consecutive allowed records into one folded row", () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls /tmp", cwd: "/tmp" },
    });
    useSessionStore.getState().enqueueConfirm({
      call_id: "c2",
      tool: "exec.bash",
      args: { cmd: "pwd", cwd: "/tmp" },
    });
    useSessionStore.getState().enqueueConfirm({
      call_id: "c3",
      tool: "fs.read",
      args: { path: "/tmp/a.md" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);
    useSessionStore.getState().resolveConfirm("c2", true);
    useSessionStore.getState().resolveConfirm("c3", true);

    const confirms = useSessionStore
      .getState()
      .messages.map((m) => m.confirm!)
      .filter(Boolean);

    render(<ChatConfirmRecordGroup confirms={confirms} />);

    expect(screen.getByText("已允许 3 项操作")).toBeInTheDocument();
    const group = screen.getByTestId("message-permission-record-group");
    expect(group).not.toHaveAttribute("open");
  });

  it("expands the grouped records when the summary is clicked", async () => {
    useSessionStore.getState().enqueueConfirm({
      call_id: "c1",
      tool: "exec.bash",
      args: { cmd: "ls", cwd: "/tmp" },
    });
    useSessionStore.getState().enqueueConfirm({
      call_id: "c2",
      tool: "exec.bash",
      args: { cmd: "pwd", cwd: "/tmp" },
    });
    useSessionStore.getState().resolveConfirm("c1", true);
    useSessionStore.getState().resolveConfirm("c2", true);

    const confirms = useSessionStore
      .getState()
      .messages.map((m) => m.confirm!)
      .filter(Boolean);

    render(<ChatConfirmRecordGroup confirms={confirms} />);
    const group = screen.getByTestId("message-permission-record-group");
    await userEvent.click(screen.getByText("已允许 2 项操作"));
    expect(group).toHaveAttribute("open");
  });
});
