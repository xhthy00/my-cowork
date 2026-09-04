/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatBar from "../../renderer/src/components/chat/ChatBar";
import { useSessionsStore } from "../../renderer/src/store/sessions";

const BACKEND_URL = "http://127.0.0.1:8000";

class MockReadableStream {
  private chunks: string[];
  private reader?: { read: () => Promise<{ done: boolean; value?: Uint8Array }> };

  constructor(chunks: string[]) {
    this.chunks = chunks;
  }

  getReader() {
    const encoder = new TextEncoder();
    let i = 0;
    this.reader = {
      read: async () => {
        if (i >= this.chunks.length) return { done: true };
        const chunk = this.chunks[i++];
        return { done: false, value: encoder.encode(chunk) };
      },
    };
    return this.reader;
  }
}

function makeResponse(chunks: string[]): Response {
  return {
    ok: true,
    status: 200,
    body: new MockReadableStream(chunks) as unknown as ReadableStream<Uint8Array>,
  } as Response;
}

describe("ChatBar", () => {
  let originalFetch: typeof fetch;

  beforeEach(async () => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue(makeResponse([])) as unknown as typeof fetch;
    window.api = {
      ...window.api,
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
      getKey: vi.fn().mockResolvedValue(null),
      restartBackend: vi.fn().mockResolvedValue(BACKEND_URL),
    };
    const { useSessionStore } = await import("../../renderer/src/store/session");
    useSessionStore.setState({
      messages: [],
      contextTokens: 0,
      contextLimit: 0,
      budgetMaxTokens: 200_000,
      runStatus: "idle",
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("POSTs user input to /api/chat and starts SSE stream", async () => {
    const onEvent = vi.fn();
    render(<ChatBar onEvent={onEvent} />);

    const input = screen.getByRole("textbox");
    await userEvent.type(input, "写 hello.txt");
    await userEvent.click(screen.getByTitle("发送"));

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${BACKEND_URL}/api/chat`,
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find((c) =>
      String(c[0]).includes("/api/chat"),
    );
    expect(call).toBeTruthy();
    const body = JSON.parse(call![1].body as string);
    expect(body).toMatchObject({
      text: "写 hello.txt",
      session_mode: "single-agent",
      memory_enabled: true,
      space_id: "space-local",
    });
  });

  it("includes prior conversation history on follow-up", async () => {
    const { useSessionStore } = await import("../../renderer/src/store/session");
    useSessionStore.setState({
      messages: [
        { id: "u1", role: "user", content: "写宜昌旅游攻略" },
        {
          id: "a1",
          role: "assistant",
          content: "宜昌三日游…",
          artifacts: [{ name: "宜昌.docx", path: "/tmp/宜昌.docx", kind: "docx" }],
        },
      ],
    });
    const onEvent = vi.fn();
    render(<ChatBar onEvent={onEvent} />);

    await userEvent.type(screen.getByRole("textbox"), "生成 ppt");
    await userEvent.click(screen.getByTitle("发送"));

    const call = (globalThis.fetch as any).mock.calls.find((c: any[]) =>
      String(c[0]).includes("/api/chat"),
    );
    expect(call).toBeTruthy();
    const body = JSON.parse(call[1].body);
    expect(body.text).toBe("生成 ppt");
    expect(body.history).toEqual([
      { role: "user", content: "写宜昌旅游攻略" },
      {
        role: "assistant",
        content: "宜昌三日游…\n\n[已生成文件: /tmp/宜昌.docx]",
      },
    ]);
  });

  it("parses SSE events and forwards them", async () => {
    const onEvent = vi.fn();
    const chunks = [
      'data: {"type":"step.delta","payload":{"delta":"hi"}}\n\n',
      'data: {"type":"step.delta","payload":{"delta":" there"}}\n\n',
    ];
    (globalThis.fetch as any).mockResolvedValue(makeResponse(chunks));

    render(<ChatBar onEvent={onEvent} />);
    await userEvent.type(screen.getByRole("textbox"), "test");
    await userEvent.click(screen.getByTitle("发送"));

    // Allow microtasks to run.
    await new Promise((r) => setTimeout(r, 0));

    expect(onEvent).toHaveBeenCalledWith(
      { type: "step.delta", payload: { delta: "hi" } },
      undefined,
    );
    expect(onEvent).toHaveBeenCalledWith(
      { type: "step.delta", payload: { delta: " there" } },
      undefined,
    );
  });

  it("shows a visible error when backend is not connected", async () => {
    window.api.getBackendUrl = vi.fn().mockResolvedValue("");
    window.api.restartBackend = vi.fn().mockResolvedValue("");
    const onEvent = vi.fn();
    render(<ChatBar onEvent={onEvent} />);

    await userEvent.type(screen.getByRole("textbox"), "写 hello.txt");
    await userEvent.click(screen.getByTitle("发送"));

    await waitFor(() => {
      expect(onEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "step.delta",
          payload: expect.objectContaining({
            delta: expect.stringContaining("后端未连接"),
          }),
        }),
        undefined,
      );
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(window.api.restartBackend).toHaveBeenCalled();
  });

  it("starts the backend on send when it is not yet connected", async () => {
    window.api.getBackendUrl = vi.fn().mockResolvedValue("");
    window.api.restartBackend = vi.fn().mockResolvedValue(BACKEND_URL);
    render(<ChatBar onEvent={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox"), "写 hello.txt");
    await userEvent.click(screen.getByTitle("发送"));
    await waitFor(() => {
      expect(window.api.restartBackend).toHaveBeenCalled();
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${BACKEND_URL}/api/chat`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows a compact session-mode label in the composer footer", () => {
    render(<ChatBar onEvent={vi.fn()} />);
    expect(screen.getByLabelText("会话模式: 单智能体")).toBeTruthy();
  });

  it("shows a context usage ring next to the model picker", async () => {
    const { useSessionStore } = await import("../../renderer/src/store/session");
    useSessionStore.setState({
      contextTokens: 98200,
      contextLimit: 192000,
    });
    render(<ChatBar onEvent={vi.fn()} />);
    expect(screen.getByLabelText("51.1% · 98.2K / 192.0K 上下文已使用")).toBeTruthy();
  });

  it("replaces send with a stop button while a task is running", async () => {
    const { useSessionStore } = await import("../../renderer/src/store/session");
    useSessionStore.setState({ runStatus: "running" });
    const onStop = vi.fn();
    render(<ChatBar onEvent={vi.fn()} onStop={onStop} />);
    expect(screen.queryByTitle("发送")).toBeNull();
    await userEvent.click(screen.getByLabelText("停止任务"));
    expect(onStop).toHaveBeenCalled();
  });

  it("POSTs bound knowledge bases so search does not need wording in the prompt", async () => {
    useSessionsStore.setState({
      sessions: [
        {
          id: "p-kb",
          title: "test",
          spaceId: "space-local",
          workdirMode: "artifact-only",
          createdAt: 1,
          updatedAt: 1,
          status: "idle",
          boundKnowledgeBases: [
            { id: "kb1", name: "唐浩宇的知识库", source: "ima" },
          ],
        },
      ],
      activeId: "p-kb",
      messagesById: { "p-kb": [] },
    });
    render(<ChatBar onEvent={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox"), "总体集成甲级条件");
    await userEvent.click(screen.getByTitle("发送"));

    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      (c) => String(c[0]).includes("/api/chat"),
    );
    expect(call).toBeTruthy();
    const body = JSON.parse(call![1].body as string);
    expect(body.text).toBe("总体集成甲级条件");
    expect(body.knowledge_bases).toEqual([
      { id: "kb1", name: "唐浩宇的知识库", source: "ima" },
    ]);
  });

  it("lets the user bind a knowledge base from the composer picker", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RequestInfo | URL) => {
        if (String(input).includes("/api/ima/knowledge-bases")) {
          return {
            ok: true,
            json: async () => ({
              configured: true,
              items: [{ id: "kb1", name: "唐浩宇的知识库", source: "ima" }],
            }),
          } as Response;
        }
        return makeResponse([]);
      },
    );
    useSessionsStore.setState({
      sessions: [
        {
          id: "p-kb",
          title: "test",
          spaceId: "space-local",
          workdirMode: "artifact-only",
          createdAt: 1,
          updatedAt: 1,
          status: "idle",
        },
      ],
      activeId: "p-kb",
      messagesById: { "p-kb": [] },
    });
    render(<ChatBar onEvent={vi.fn()} />);
    await userEvent.click(screen.getByTitle("知识库"));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /唐浩宇的知识库/ })).toBeTruthy();
    });
    await userEvent.click(screen.getByRole("button", { name: /唐浩宇的知识库/ }));
    await waitFor(() => {
      expect(useSessionsStore.getState().sessions[0].boundKnowledgeBases).toEqual([
        { id: "kb1", name: "唐浩宇的知识库", source: "ima" },
      ]);
    });
  });

  it("reloads backend when Hub keys exist but the list API says unconfigured", async () => {
    window.api.getKey = vi.fn().mockImplementation(async (account: string) => {
      if (account === "ima:client_id") return "cid";
      if (account === "ima:api_key") return "secret";
      return null;
    });
    useSessionsStore.setState({
      sessions: [
        {
          id: "p-kb-reload",
          title: "test",
          spaceId: "space-local",
          workdirMode: "artifact-only",
          createdAt: 1,
          updatedAt: 1,
          status: "idle",
          boundKnowledgeBases: [],
        },
      ],
      activeId: "p-kb-reload",
      messagesById: { "p-kb-reload": [] },
    });
    let listed = 0;
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      async (input: RequestInfo | URL) => {
        if (String(input).includes("/api/ima/knowledge-bases")) {
          listed += 1;
          if (listed === 1) {
            return {
              ok: true,
              status: 200,
              json: async () => ({ configured: false, items: [] }),
            } as Response;
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              configured: true,
              items: [{ id: "kb1", name: "唐浩宇的知识库", source: "ima" }],
            }),
          } as Response;
        }
        return makeResponse([]);
      },
    );
    render(<ChatBar onEvent={vi.fn()} />);
    await userEvent.click(screen.getByTitle("知识库"));
    await waitFor(() => {
      expect(window.api.restartBackend).toHaveBeenCalled();
      expect(
        screen.getByRole("button", { name: /^唐浩宇的知识库/ }),
      ).toBeTruthy();
    });
  });
});
