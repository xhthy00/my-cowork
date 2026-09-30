/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MemoryView from "../../renderer/src/components/memory/MemoryView";
import { announceMemoryChanged } from "../../renderer/src/lib/memoryEvents";

const base = "http://127.0.0.1:8000";
let originalFetch: typeof fetch;
let entries: Array<{ id: number; content: string; scope: "global"; workspace: null; summary: string; created_at: number }>;
let settings: { enabled: boolean; user_rules: string };

beforeEach(() => {
  originalFetch = globalThis.fetch;
  localStorage.removeItem("my-cowork-memory-on");
  entries = [{ id: 1, content: "报告先给结论", scope: "global", workspace: null, summary: "", created_at: 1 }];
  settings = { enabled: true, user_rules: "" };
  window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue(base) };
  globalThis.fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    let payload: unknown = {};
    if (url.endsWith("/api/memory/settings")) {
      if (init?.method === "PUT") settings = { ...settings, ...JSON.parse(String(init.body)) };
      payload = settings;
    } else if (url.endsWith("/api/memory/list?limit=500")) {
      payload = { items: [...entries] };
    } else if (url.endsWith("/api/memory") && init?.method === "DELETE") {
      entries = [];
      payload = { ok: true, deleted: 1 };
    } else if (url.endsWith("/api/memory/1")) {
      if (init?.method === "PATCH") entries[0].content = JSON.parse(String(init.body)).content;
      if (init?.method === "DELETE") entries = [];
      payload = { ok: true };
    }
    return { ok: true, json: async () => payload } as Response;
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("MemoryView", () => {
  it("uses OpenWorker's toggle, learned list, then user instructions layout", async () => {
    const { container } = render(<MemoryView />);
    await screen.findByText("报告先给结论");
    expect(Array.from(container.querySelectorAll("section h3")).map((heading) => heading.textContent)).toEqual([
      "记住关于我的新信息", "我对你的了解", "你的指令",
    ]);
    expect(screen.getByRole("switch", { name: "记住关于我的新信息" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByText("手动添加")).toBeNull();
    expect(screen.queryByText("我的长期规则")).toBeNull();
  });

  it("keeps user instructions editable when new memory is disabled", async () => {
    render(<MemoryView />);
    await screen.findByText("报告先给结论");
    await userEvent.click(screen.getByRole("switch", { name: "记住关于我的新信息" }));
    await waitFor(() => expect(settings.enabled).toBe(false));
    expect(screen.getByText(/已有内容仍会使用/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "你的指令" }), { target: { value: "日期用 YYYY-MM-DD" } });
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(settings.user_rules).toBe("日期用 YYYY-MM-DD"));
  });

  it("refreshes after conversation memory changes and edits a remembered item", async () => {
    render(<MemoryView />);
    await screen.findByText("报告先给结论");
    entries.push({ id: 2, content: "使用简体中文", scope: "global", workspace: null, summary: "", created_at: 2 });
    announceMemoryChanged();
    await screen.findByText("使用简体中文");
    await userEvent.click(screen.getByRole("button", { name: "修正记忆：报告先给结论" }));
    fireEvent.change(screen.getByRole("textbox", { name: "编辑记忆 1" }), { target: { value: "报告先写摘要" } });
    await userEvent.click(within(screen.getByTestId("memory-row-1")).getByRole("button", { name: "保存" }));
    await screen.findByText("报告先写摘要");
    expect(globalThis.fetch).toHaveBeenCalledWith(`${base}/api/memory/1`, expect.objectContaining({ method: "PATCH" }));
  });

  it("confirms before forgetting all learned memories", async () => {
    render(<MemoryView />);
    await screen.findByText("报告先给结论");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "忘掉全部…" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(entries).toHaveLength(1);
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "忘掉全部…" }));
    await waitFor(() => expect(entries).toHaveLength(0));
    expect(globalThis.fetch).toHaveBeenCalledWith(`${base}/api/memory`, expect.objectContaining({ method: "DELETE" }));
  });
});
