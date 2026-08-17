/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChannelsPanel from "../../renderer/src/components/settings/channels/ChannelsPanel";

const BACKEND_URL = "http://127.0.0.1:8000";

const PLUGINS = [
  {
    plugin_id: "telegram",
    type: "telegram",
    name: "Telegram",
    enabled: false,
    connected: false,
    coming_soon: true,
    has_token: false,
  },
  {
    plugin_id: "lark",
    type: "lark",
    name: "Lark / 飞书",
    enabled: false,
    connected: false,
    coming_soon: false,
    has_token: false,
  },
  {
    plugin_id: "dingtalk",
    type: "dingtalk",
    name: "钉钉",
    enabled: false,
    connected: false,
    coming_soon: true,
    has_token: false,
  },
];

class MockEventSource {
  url: string;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  constructor(url: string) {
    this.url = url;
  }
  close() {}
}

function jsonResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => data,
  };
}

describe("ChannelsPanel", () => {
  let originalFetch: typeof fetch;
  let originalES: typeof EventSource | undefined;
  const calls: { url: string; method: string; body?: unknown }[] = [];

  beforeEach(() => {
    calls.length = 0;
    originalFetch = globalThis.fetch;
    originalES = (globalThis as unknown as { EventSource?: typeof EventSource }).EventSource;
    (globalThis as unknown as { EventSource: typeof EventSource }).EventSource =
      MockEventSource as unknown as typeof EventSource;

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || "GET").toUpperCase();
      let body: unknown;
      if (init?.body) {
        try {
          body = JSON.parse(String(init.body));
        } catch {
          body = init.body;
        }
      }
      calls.push({ url, method, body });

      if (url.endsWith("/api/channel/plugins") && method === "GET") {
        return jsonResponse(PLUGINS) as Response;
      }
      if (url.endsWith("/api/channel/plugins/test") && method === "POST") {
        return jsonResponse({ success: true, bot_username: "lark" }) as Response;
      }
      if (url.endsWith("/api/channel/plugins/enable") && method === "POST") {
        return jsonResponse({ ok: true }) as Response;
      }
      if (url.endsWith("/api/channel/pairings")) {
        return jsonResponse([]) as Response;
      }
      if (url.endsWith("/api/channel/users")) {
        return jsonResponse([]) as Response;
      }
      if (url.includes("/api/channel/settings/")) {
        return jsonResponse({ platform: "lark", assistant: null, default_model: null }) as Response;
      }
      if (url.endsWith("/api/assistants")) {
        return jsonResponse({ assistants: [] }) as Response;
      }
      return jsonResponse({}) as Response;
    }) as unknown as typeof fetch;

    window.api = {
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
      restartBackend: vi.fn().mockResolvedValue(BACKEND_URL),
      getKey: vi.fn().mockResolvedValue(null),
      setKey: vi.fn().mockResolvedValue(undefined),
      getModels: vi.fn().mockResolvedValue({ profiles: [], activeId: null }),
    } as unknown as typeof window.api;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalES) {
      (globalThis as unknown as { EventSource: typeof EventSource }).EventSource = originalES;
    }
  });

  it("renders Telegram, 飞书, 钉钉 cards with coming soon on the outer two", async () => {
    render(<ChannelsPanel />);
    expect(await screen.findByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("飞书")).toBeInTheDocument();
    expect(screen.getByText("钉钉")).toBeInTheDocument();
    expect(screen.getAllByText("即将推出")).toHaveLength(2);
    expect(screen.getByRole("switch", { name: "启用Telegram" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "启用钉钉" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "启用飞书" })).not.toBeDisabled();
  });

  it("toasts when enabling 飞书 without credentials", async () => {
    render(<ChannelsPanel />);
    await screen.findByText("飞书");
    await userEvent.click(screen.getByRole("switch", { name: "启用飞书" }));
    expect(await screen.findByTestId("channel-toast")).toHaveTextContent(
      "请输入 App ID 和 App Secret",
    );
  });

  it("shows inline error next to 测试并连接 when secret is missing", async () => {
    render(<ChannelsPanel />);
    await screen.findByLabelText("飞书 App ID");
    await userEvent.type(screen.getByLabelText("飞书 App ID"), "cli_abc");
    await userEvent.click(screen.getByRole("button", { name: "测试并连接" }));
    expect(
      await screen.findAllByText("请输入 App ID 和 App Secret"),
    ).not.toHaveLength(0);
    expect(calls.some((c) => c.url.endsWith("/api/channel/plugins/test"))).toBe(
      false,
    );
  });

  it("calls test then enable on 测试并连接", async () => {
    render(<ChannelsPanel />);
    await screen.findByLabelText("飞书 App ID");
    await userEvent.type(screen.getByLabelText("飞书 App ID"), "cli_abc");
    await userEvent.type(screen.getByLabelText("飞书 App Secret"), "sec_abc");
    await userEvent.click(screen.getByRole("button", { name: "测试并连接" }));

    await waitFor(() => {
      const testCall = calls.find((c) => c.url.endsWith("/api/channel/plugins/test"));
      const enableCall = calls.find((c) => c.url.endsWith("/api/channel/plugins/enable"));
      expect(testCall).toBeTruthy();
      expect(enableCall).toBeTruthy();
      expect(calls.indexOf(testCall!)).toBeLessThan(calls.indexOf(enableCall!));
    });
    expect(window.api.setKey).toHaveBeenCalledWith("lark:app_id", "cli_abc");
    expect(window.api.setKey).toHaveBeenCalledWith("lark:app_secret", "sec_abc");
  });

  it("restarts backend when channel routes return Not Found", async () => {
    let pluginGets = 0;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || "GET").toUpperCase();
      if (url.endsWith("/api/channel/plugins") && method === "GET") {
        pluginGets += 1;
        if (pluginGets === 1) {
          return jsonResponse({ detail: "Not Found" }, false, 404) as Response;
        }
        return jsonResponse(PLUGINS) as Response;
      }
      if (url.endsWith("/api/channel/pairings")) return jsonResponse([]) as Response;
      if (url.endsWith("/api/channel/users")) return jsonResponse([]) as Response;
      if (url.includes("/api/channel/settings/")) {
        return jsonResponse({ platform: "lark", assistant: null, default_model: null }) as Response;
      }
      if (url.endsWith("/api/assistants")) return jsonResponse({ assistants: [] }) as Response;
      return jsonResponse({}) as Response;
    }) as unknown as typeof fetch;

    render(<ChannelsPanel />);
    await waitFor(() => {
      expect(window.api.restartBackend).toHaveBeenCalled();
    });
    expect(await screen.findByText("飞书")).toBeInTheDocument();
  });
});
