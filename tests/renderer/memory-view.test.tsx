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
  it("preserves manual entry and project scopes alongside learned memories", async () => {
    const { container } = render(<MemoryView />);
    await screen.findByText("报告先给结论");
    expect(Array.from(container.querySelectorAll("section h3")).map((heading) => heading.textContent)).toEqual([
      "手动添加", "已保存的记忆",
    ]);
    expect(screen.getByRole("switch", { name: "保存新记忆" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("textbox", { name: "记忆内容" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "记忆范围" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "我的长期规则" })).toBeTruthy();
  });

  it("keeps user instructions editable when new memory is disabled", async () => {
    render(<MemoryView />);
    await screen.findByText("报告先给结论");
    await userEvent.click(screen.getByRole("switch", { name: "保存新记忆" }));
    await waitFor(() => expect(settings.enabled).toBe(false));
    expect(screen.getByText(/已有记忆仍会用于新会话/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "我的长期规则" }), { target: { value: "日期用 YYYY-MM-DD" } });
    await userEvent.click(screen.getByRole("button", { name: "保存规则" }));
    await waitFor(() => expect(settings.user_rules).toBe("日期用 YYYY-MM-DD"));
  });

  it("refreshes after conversation memory changes and edits a remembered item", async () => {
    render(<MemoryView />);
    await screen.findByText("报告先给结论");
    fireEvent.change(screen.getByRole("textbox", { name: "我的长期规则" }), { target: { value: "未保存的规则" } });
    entries.push({ id: 2, content: "使用简体中文", scope: "global", workspace: null, summary: "", created_at: 2 });
    announceMemoryChanged();
    await screen.findByText("使用简体中文");
    expect(screen.getByRole("textbox", { name: "我的长期规则" })).toHaveValue("未保存的规则");
    await userEvent.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    fireEvent.change(screen.getByRole("textbox", { name: "编辑记忆 1" }), { target: { value: "报告先写摘要" } });
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    await screen.findByText("报告先写摘要");
    expect(globalThis.fetch).toHaveBeenCalledWith(`${base}/api/memory/1`, expect.objectContaining({ method: "PATCH" }));
  });

  it("confirms before forgetting all learned memories", async () => {
    render(<MemoryView />);
    await screen.findByText("报告先给结论");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "删除全部" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(entries).toHaveLength(1);
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "删除全部" }));
    await waitFor(() => expect(entries).toHaveLength(0));
    expect(globalThis.fetch).toHaveBeenCalledWith(`${base}/api/memory`, expect.objectContaining({ method: "DELETE" }));
  });
});
