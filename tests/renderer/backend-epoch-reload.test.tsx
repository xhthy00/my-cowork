/** @vitest-environment jsdom */

import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MemoryView from "../../renderer/src/components/memory/MemoryView";
import AssistantsView from "../../renderer/src/components/hub/AssistantsView";
import SkillsView from "../../renderer/src/components/skills/SkillsView";

const BACKEND_URL = "http://127.0.0.1:8000";

describe("pages loaded before the backend is up", () => {
  const originalFetch = globalThis.fetch;
  let readyCbs: Array<(url: string) => void>;

  beforeEach(() => {
    readyCbs = [];
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/settings")
        ? { enabled: true, user_rules: "" }
        : { items: [{ id: 1, scope: "global", workspace: null, content: "喜欢简洁的回复", summary: null, created_at: 0 }] };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;
    window.api = {
      getBackendUrl: vi.fn().mockResolvedValue(""),
      onBackendReady: vi.fn((cb: (url: string) => void) => {
        readyCbs.push(cb);
        return () => {};
      }),
    } as unknown as typeof window.api;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("memory page recovers from '后端未连接' once the backend reports ready", async () => {
    render(<MemoryView />);
    expect(await screen.findByText("后端未连接，请检查本地服务或前往设置 → 模型配置/上下文")).toBeInTheDocument();

    window.api.getBackendUrl = vi.fn().mockResolvedValue(BACKEND_URL);
    act(() => readyCbs.forEach((cb) => cb(BACKEND_URL)));

    expect(await screen.findByText("喜欢简洁的回复")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("后端未连接，请检查本地服务或前往设置 → 模型配置/上下文")).not.toBeInTheDocument());
  });

  it.each([
    ["needs-model", "尚未配置模型，请前往设置 → 模型配置/上下文完成配置"],
    ["starting", "本地服务正在启动，请稍候"],
    ["failed", "本地服务启动失败：测试启动失败"],
  ])("shows the %s state on the assistants page", async (state, message) => {
    window.api.getBackendStatus = vi.fn().mockResolvedValue({ state, error: "测试启动失败" });
    render(<AssistantsView />);
    expect(await screen.findByText(message)).toBeInTheDocument();
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ assistants: [] })));
    window.api.getBackendUrl = vi.fn().mockResolvedValue(BACKEND_URL);
    act(() => readyCbs.forEach((cb) => cb(BACKEND_URL)));
    await waitFor(() => expect(screen.queryByText(message)).not.toBeInTheDocument());
  });

  it("reloads local skills after first model configuration", async () => {
    window.api.getBackendStatus = vi.fn().mockResolvedValue({ state: "needs-model", error: "" });
    render(<SkillsView />);
    expect((await screen.findAllByText("尚未配置模型，请前往设置 → 模型配置/上下文完成配置")).length).toBeGreaterThan(0);
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ skills: [], total: 0 })));
    window.api.getBackendUrl = vi.fn().mockResolvedValue(BACKEND_URL);
    act(() => readyCbs.forEach((cb) => cb(BACKEND_URL)));
    await waitFor(() => expect(screen.queryByText("尚未配置模型，请前往设置 → 模型配置/上下文完成配置")).not.toBeInTheDocument());
  });
});
