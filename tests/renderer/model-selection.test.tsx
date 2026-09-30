/** @vitest-environment jsdom */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import ChatBar from "../../renderer/src/components/chat/ChatBar";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { useSessionStore } from "../../renderer/src/store/session";

const profile = {
  id: "a",
  name: "工作模型",
  model: "test-a",
  provider: "openai_compat" as const,
  baseUrl: "https://api.openai.com/v1",
  reasoning: { effort: "high" },
};
beforeEach(() => {
  useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
  useSessionsStore.getState().createSession("讨论");
  useSessionStore.setState({
    messages: [],
    contextTokens: 0,
    contextLimit: 0,
    runStatus: "idle",
  });
  window.api = {
    ...window.api,
    getModels: vi
      .fn()
      .mockResolvedValue({ profiles: [profile], activeId: "a" }),
    getBackendUrl: vi.fn().mockResolvedValue("http://backend"),
    getModelCatalog: vi.fn().mockResolvedValue({
      updatedAt: "test",
      models: [
        {
          id: "openai/test-a",
          provider: "openai",
          model: "test-a",
          name: "Test A",
          reasoning: true,
          options: [{ type: "effort", values: ["low", "high"] }],
          context: 128000,
        },
      ],
    }),
    onModelCatalogChanged: vi.fn(() => () => {}),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        tokens: 32000,
        limit: 128000,
        input_budget: 94208,
        trigger: 94208,
      }),
      body: { getReader: () => ({ read: async () => ({ done: true }) }) },
    })),
  );
});

it("keeps reasoning inside the model menu and explicitly resets legacy defaults", async () => {
  render(<ChatBar onEvent={vi.fn()} />);
  const trigger = await screen.findByRole("button", { name: "工作模型 · 高" });
  expect(screen.queryByLabelText("思考强度")).not.toBeInTheDocument();
  await userEvent.click(trigger);
  expect(screen.queryByText("自定义模型")).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("menuitemradio", { name: "服务默认" }),
  );
  await userEvent.keyboard("{Escape}");
  await userEvent.type(screen.getByRole("textbox"), "继续");
  await userEvent.click(screen.getByTitle("发送"));
  await waitFor(() =>
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
    ).toBe(true),
  );
  const call = vi
    .mocked(fetch)
    .mock.calls.find(([url]) => String(url).endsWith("/api/chat"))!;
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({
    model_profile_id: "a",
    reasoning: {},
  });
});

it("shows context details on demand and uses the same effort for manual compression", async () => {
  render(<ChatBar onEvent={vi.fn()} />);
  await screen.findByRole("button", { name: "工作模型 · 高" });
  expect(
    screen.queryByRole("button", { name: "压缩对话" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /上下文用量/ }));
  expect(await screen.findByText("94,208")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("menuitem", { name: "压缩对话" }));
  await waitFor(() =>
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/compact")),
    ).toBe(true),
  );
  const call = vi
    .mocked(fetch)
    .mock.calls.find(([url]) => String(url).endsWith("/compact"))!;
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({
    reasoning: { effort: "high" },
  });
});

it("does not change an initialized conversation when the global default changes", async () => {
  render(<ChatBar onEvent={vi.fn()} />);
  await screen.findByRole("button", { name: "工作模型 · 高" });
  await waitFor(() =>
    expect(useSessionsStore.getState().sessions[0].modelProfileId).toBe("a"),
  );
  vi.mocked(window.api.getModels).mockResolvedValue({
    profiles: [profile, { ...profile, id: "b", name: "其他模型" }],
    activeId: "b",
  });
  window.dispatchEvent(new Event("my-cowork:models-changed"));
  await waitFor(() => expect(window.api.getModels).toHaveBeenCalledTimes(2));
  expect(
    screen.getByRole("button", { name: "工作模型 · 高" }),
  ).toBeInTheDocument();
});

it("remembers each model's selection and does not carry effort to a model without it", async () => {
  vi.mocked(window.api.getModels).mockResolvedValue({
    profiles: [
      profile,
      { ...profile, id: "b", model: "plain", name: "普通模型", reasoning: {} },
    ],
    activeId: "a",
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "工作模型 · 高" }),
  );
  await userEvent.click(screen.getByRole("menuitemradio", { name: "低" }));
  await userEvent.click(
    screen.getByRole("menuitemradio", { name: "普通模型" }),
  );
  expect(
    screen.queryByRole("group", { name: "思考强度" }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("menuitemradio", { name: "工作模型" }),
  );
  expect(screen.getByRole("menuitemradio", { name: "低" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});

it("blocks unsupported saved effort and preserves the draft until reset", async () => {
  const id = useSessionsStore.getState().activeId!;
  useSessionsStore.getState().touchSession(id, {
    modelProfileId: "a",
    modelReasoning: { a: { effort: "max" } },
  });
  render(<ChatBar onEvent={vi.fn()} />);
  const trigger = await screen.findByRole("button", {
    name: "工作模型 · 检查选项",
  });
  await userEvent.type(screen.getByRole("textbox"), "不能丢失的草稿");
  await userEvent.click(screen.getByTitle("发送"));
  expect(
    vi
      .mocked(fetch)
      .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
  ).toBe(false);
  expect(screen.getByRole("textbox")).toHaveTextContent("不能丢失的草稿");
  expect(screen.getByRole("alert")).toHaveTextContent("不支持");
  await userEvent.click(trigger);
  await userEvent.click(
    screen.getByRole("menuitemradio", { name: "服务默认" }),
  );
  await userEvent.keyboard("{Escape}");
  expect(
    screen.getByRole("button", { name: "工作模型 · 默认" }),
  ).toBeInTheDocument();
});

it("removes legacy thinking toggles and sends only the supported effort", async () => {
  vi.mocked(window.api.getModels).mockResolvedValue({
    profiles: [{ ...profile, reasoning: { effort: "low", enabled: false } }],
    activeId: "a",
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "工作模型 · 低" }),
  );
  expect(screen.queryByText("思考模式")).not.toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await userEvent.type(screen.getByRole("textbox"), "继续");
  await userEvent.click(screen.getByTitle("发送"));
  await waitFor(() =>
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
    ).toBe(true),
  );
  const call = vi
    .mocked(fetch)
    .mock.calls.find(([url]) => String(url).endsWith("/api/chat"))!;
  expect(JSON.parse(String(call[1]?.body)).reasoning).toEqual({
    effort: "low",
  });
});

it("warns only after switching models in an existing conversation without calling chat or compact", async () => {
  vi.mocked(window.api.getModels).mockResolvedValue({
    profiles: [profile, { ...profile, id: "b", name: "小模型" }],
    activeId: "a",
  });
  useSessionStore.setState({
    messages: [
      { id: "m", role: "user", content: "原有对话", timestamp: Date.now() },
    ],
  });
  vi.mocked(fetch).mockResolvedValue({
    ok: true,
    json: async () => ({ tokens: 700000, limit: 300000, trigger: 240000 }),
  } as Response);
  render(<ChatBar onEvent={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "工作模型 · 高" }),
  );
  expect(
    screen.queryByText("对话中更换模型可能降低性能表现"),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("menuitemradio", { name: "小模型" }));
  await userEvent.keyboard("{Escape}");
  expect(
    await screen.findByText("对话中更换模型可能降低性能表现"),
  ).toBeInTheDocument();
  expect(
    await screen.findByText("发送前将自动整理较早对话"),
  ).toBeInTheDocument();
  expect(
    vi
      .mocked(fetch)
      .mock.calls.every(([url]) => !/\/(chat|compact)$/.test(String(url))),
  ).toBe(true);
});

it("restores the input when automatic context preparation fails", async () => {
  const originalFetch = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (!String(url).endsWith("/api/chat")) return originalFetch(url, init);
    let done = false;
    return {
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (done) return { done: true };
            done = true;
            return {
              done: false,
              value: new TextEncoder().encode(
                'data: {"type":"graph.end","status":"error","error_code":"context_preparation","error":"压缩失败，原上下文已保留"}\n\n',
              ),
            };
          },
        }),
      },
    } as Response;
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await screen.findByRole("button", { name: "工作模型 · 高" });
  await userEvent.type(screen.getByRole("textbox"), "不能丢失的本次输入");
  await userEvent.click(screen.getByTitle("发送"));
  await waitFor(() =>
    expect(screen.getByRole("textbox")).toHaveTextContent("不能丢失的本次输入"),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("压缩失败");
});

it("does not invent strength choices for a toggle-only model", async () => {
  vi.mocked(window.api.getModels).mockResolvedValue({
    profiles: [
      {
        ...profile,
        baseUrl: "https://api.deepseek.com",
        reasoning: { enabled: false },
      },
    ],
    activeId: "a",
  });
  vi.mocked(window.api.getModelCatalog).mockResolvedValue({
    updatedAt: "test",
    models: [
      {
        id: "deepseek/test-a",
        model: "test-a",
        provider: "deepseek",
        name: "Test A",
        reasoning: true,
        options: [{ type: "toggle" }],
        context: 128000,
      },
    ],
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "工作模型", exact: true }),
  );
  expect(screen.queryByText("思考模式")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("group", { name: "思考强度" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("思考设置")).not.toBeInTheDocument();
});

it("keeps a newer draft intact and offers recovery of the failed input and attachments", async () => {
  const originalFetch = vi.mocked(fetch).getMockImplementation()!;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (!String(url).endsWith("/api/chat")) return originalFetch(url, init);
    let done = false;
    return {
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (done) return { done: true };
            done = true;
            await gate;
            return {
              done: false,
              value: new TextEncoder().encode(
                'data: {"type":"graph.end","status":"error","error_code":"context_preparation","error":"压缩失败"}\n\n',
              ),
            };
          },
        }),
      },
    } as Response;
  });
  window.api.selectFile = vi.fn().mockResolvedValue({
    success: true,
    files: [{ filePath: "C:/report.txt", fileName: "report.txt" }],
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await screen.findByRole("button", { name: "工作模型 · 高" });
  await userEvent.click(screen.getByRole("button", { name: "添加文件或照片" }));
  await screen.findByText("report.txt");
  await userEvent.type(screen.getByRole("textbox"), "原始输入");
  await userEvent.click(screen.getByTitle("发送"));
  await waitFor(() =>
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
    ).toBe(true),
  );
  await userEvent.type(screen.getByRole("textbox"), "新写的草稿");
  await act(async () => {
    release();
  });
  await screen.findByRole("alert");
  expect(screen.getByRole("textbox")).toHaveTextContent("新写的草稿");
  expect(screen.getByRole("textbox")).not.toHaveTextContent("原始输入");
  await userEvent.click(screen.getByRole("button", { name: "恢复上次输入" }));
  expect(screen.getByRole("textbox")).toHaveTextContent("新写的草稿");
  expect(screen.getByRole("textbox")).toHaveTextContent("原始输入");
  expect(screen.getByText("report.txt")).toBeInTheDocument();
});

it("stores a failed draft with its original conversation when another conversation is active", async () => {
  const originalId = useSessionsStore.getState().activeId!;
  const originalFetch = vi.mocked(fetch).getMockImplementation()!;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (!String(url).endsWith("/api/chat")) return originalFetch(url, init);
    let done = false;
    return {
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (done) return { done: true };
            done = true;
            await gate;
            return {
              done: false,
              value: new TextEncoder().encode(
                'data: {"type":"graph.end","status":"error","error_code":"context_preparation","error":"压缩失败"}\n\n',
              ),
            };
          },
        }),
      },
    } as Response;
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await screen.findByRole("button", { name: "工作模型 · 高" });
  await userEvent.type(screen.getByRole("textbox"), "属于原会话的输入");
  await userEvent.click(screen.getByTitle("发送"));
  await waitFor(() =>
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
    ).toBe(true),
  );
  await act(async () => {
    useSessionsStore.getState().createSession("另一个对话");
  });
  await act(async () => {
    release();
  });
  await waitFor(() =>
    expect(
      useSessionsStore
        .getState()
        .sessions.find((s) => s.id === originalId)
        ?.failedDraft?.text.trim(),
    ).toBe("属于原会话的输入"),
  );
  expect(screen.getByRole("textbox")).not.toHaveTextContent("属于原会话的输入");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await act(async () => {
    useSessionsStore.getState().setActive(originalId);
  });
  expect(screen.getByRole("textbox")).toHaveTextContent("属于原会话的输入");
});
