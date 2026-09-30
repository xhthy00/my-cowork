/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChatBar from "../../renderer/src/components/chat/ChatBar";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { useSessionStore } from "../../renderer/src/store/session";

const model = {
  id: "a",
  name: "Model A",
  model: "a",
  provider: "openai_compat" as const,
  baseUrl: "https://api.openai.com/v1",
};
let projectId: string;
beforeEach(() => {
  useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
  projectId = useSessionsStore.getState().createSession("command test");
  useSessionStore.setState({
    messages: [],
    contextTokens: 0,
    contextLimit: 64000,
    runStatus: "idle",
  });
  window.api = {
    ...window.api,
    getBackendUrl: vi.fn().mockResolvedValue("http://backend"),
    getModels: vi.fn().mockResolvedValue({ profiles: [model], activeId: "a" }),
    getModelCatalog: vi
      .fn()
      .mockResolvedValue({
        updatedAt: "test",
        models: [
          {
            id: "openai/a",
            provider: "openai",
            model: "a",
            name: "Model A",
            reasoning: true,
            options: [{ type: "effort", values: ["low", "high"] }],
            context: 64000,
          },
        ],
      }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (url: string) =>
        ({
          ok: true,
          json: async () =>
            url.endsWith("/compact")
              ? { before_tokens: 1000, tokens: 100, limit: 64000 }
              : { tokens: 1000, limit: 64000 },
          body: { getReader: () => ({ read: async () => ({ done: true }) }) },
        }) as Response,
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

it("refreshes reasoning controls after the main process synchronizes a new catalog", async () => {
  let changed: (() => void) | undefined;
  window.api.onModelCatalogChanged = vi.fn((cb) => {
    changed = cb;
    return () => {};
  });
  render(<ChatBar onEvent={vi.fn()} />);
  await screen.findByRole("button", { name: "Model A · 默认" });
  vi.mocked(window.api.getModelCatalog).mockResolvedValue({
    updatedAt: "new",
    models: [
      {
        id: "openai/a",
        provider: "openai",
        model: "a",
        name: "A",
        reasoning: true,
        options: [{ type: "effort", values: ["low", "high", "max"] }],
        context: 128000,
      },
    ],
  });
  await userEvent.click(screen.getByRole("button", { name: "Model A · 默认" }));
  changed?.();
  expect(
    await screen.findByRole("menuitemradio", { name: "最高" }),
  ).toBeInTheDocument();
});

it("runs /压缩 with focus without creating a chat task or adding a user turn", async () => {
  const onSend = vi.fn();
  render(<ChatBar onEvent={vi.fn()} onSend={onSend} />);
  await screen.findByRole("button", { name: "Model A · 默认" });
  await userEvent.type(screen.getByRole("textbox"), "/压缩 保留关于预算的讨论");
  await userEvent.click(screen.getByTitle("发送"));
  expect(await screen.findByText(/压缩完成/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "http://backend/api/context/compact",
    expect.objectContaining({
      body: JSON.stringify({
        session_id: projectId,
        model_profile_id: "a",
        reasoning: {},
        focus: "保留关于预算的讨论",
      }),
    }),
  );
  expect(onSend).not.toHaveBeenCalled();
  expect(
    vi
      .mocked(fetch)
      .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
  ).toBe(false);
  expect(useSessionStore.getState().contextTokens).toBe(100);
});

it("preserves IME composition and offers Chinese completion on Tab", async () => {
  render(<ChatBar onEvent={vi.fn()} />);
  const input = screen.getByRole("textbox");
  await userEvent.type(input, "/压");
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  expect(
    vi
      .mocked(fetch)
      .mock.calls.some(([url]) => String(url).endsWith("/api/chat")),
  ).toBe(false);
  expect(screen.getByRole("listbox", { name: "中文命令" })).toBeInTheDocument();
  expect(document.activeElement).toBe(input);
  await userEvent.keyboard("{Tab}");
  await waitFor(() => expect(input.textContent).toContain("/压缩"));
  expect(input.textContent).toContain("/压缩");
});

it("captures the conversation's actual effort choice in its next request", async () => {
  render(<ChatBar onEvent={vi.fn()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Model A · 默认" }),
  );
  await userEvent.click(screen.getByRole("menuitemradio", { name: "高" }));
  await userEvent.keyboard("{Escape}");
  await userEvent.type(screen.getByRole("textbox"), "继续讨论");
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
    reasoning: { effort: "high" },
  });
});
