/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor, within } from "@testing-library/react";
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
  {
    plugin_id: "weixin",
    type: "weixin",
    name: "微信 ClawBot",
    enabled: false,
    connected: false,
    coming_soon: false,
    has_token: false,
  },
];

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  closed = false;
  private listeners: Record<string, Array<(ev: MessageEvent) => void>> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, cb: (ev: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(cb);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const ev = { data: JSON.stringify(data) } as MessageEvent;
    for (const cb of this.listeners[type] || []) cb(ev);
  }
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
    MockEventSource.instances = [];
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
      if (url.endsWith("/api/channel/plugins/disable") && method === "POST") {
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

  it("renders Telegram, 飞书, 钉钉, 微信 cards with coming soon on telegram and dingtalk", async () => {
    render(<ChannelsPanel />);
    expect(await screen.findByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("飞书")).toBeInTheDocument();
    expect(screen.getByText("钉钉")).toBeInTheDocument();
    expect(screen.getByText("微信")).toBeInTheDocument();
    expect(screen.getAllByText("即将推出")).toHaveLength(2);
    expect(screen.getByRole("switch", { name: "启用Telegram" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "启用钉钉" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "启用飞书" })).not.toBeDisabled();
    expect(screen.getByRole("switch", { name: "启用微信" })).not.toBeDisabled();
  });

  it("toasts when enabling 飞书 without credentials", async () => {
    render(<ChannelsPanel />);
    await screen.findByText("飞书");
    await userEvent.click(screen.getByRole("switch", { name: "启用飞书" }));
    expect(await screen.findByTestId("channel-toast")).toHaveTextContent(
      "请输入 App ID 和 App Secret",
    );
  });

  it("toasts when enabling 微信 without a scan", async () => {
    render(<ChannelsPanel />);
    await screen.findByText("微信");
    await userEvent.click(screen.getByRole("switch", { name: "启用微信" }));
    expect(await screen.findByTestId("channel-toast")).toHaveTextContent(
      "请先使用微信扫码登录",
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

  it("opens WeChat login SSE and enables with snake_case credentials after done", async () => {
    render(<ChannelsPanel />);
    await screen.findByText("微信");
    await userEvent.click(screen.getByRole("button", { name: "展开微信" }));
    const weixinCard = document.querySelector("[data-channel-id='weixin']");
    expect(weixinCard).toBeTruthy();
    expect(within(weixinCard as HTMLElement).queryByRole("button", { name: "测试并连接" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "扫码登录" }));

    await waitFor(() => {
      expect(MockEventSource.instances.some((es) => es.url.endsWith("/api/channel/weixin/login"))).toBe(
        true,
      );
    });
    const es = MockEventSource.instances.find((x) =>
      x.url.endsWith("/api/channel/weixin/login"),
    )!;
    es.emit("qr", { qrcodeData: "hello-qr" });
    await waitFor(() => {
      expect(screen.getAllByText("请用微信扫描二维码").length).toBeGreaterThan(0);
    });
    es.emit("scanned", {});
    await screen.findByText("已扫码，等待确认...");
    es.emit("done", {
      accountId: "bot-acc",
      botToken: "bot-tok",
      baseUrl: "https://ilinkai.weixin.qq.com",
    });

    await waitFor(() => {
      const enableCall = calls.find(
        (c) =>
          c.url.endsWith("/api/channel/plugins/enable") &&
          (c.body as { plugin_id?: string })?.plugin_id === "weixin",
      );
      expect(enableCall?.body).toEqual({
        plugin_id: "weixin",
        config: { credentials: { account_id: "bot-acc", bot_token: "bot-tok" } },
      });
    });
    expect(window.api.setKey).toHaveBeenCalledWith("weixin:account_id", "bot-acc");
    expect(window.api.setKey).toHaveBeenCalledWith("weixin:bot_token", "bot-tok");
    expect(window.api.setKey).toHaveBeenCalledWith(
      "weixin:base_url",
      "https://ilinkai.weixin.qq.com",
    );
    expect(es.closed).toBe(true);
  });

  it("closes WeChat login EventSource on unmount", async () => {
    const { unmount } = render(<ChannelsPanel />);
    await screen.findByText("微信");
    await userEvent.click(screen.getByRole("button", { name: "展开微信" }));
    await userEvent.click(screen.getByRole("button", { name: "扫码登录" }));
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });
    const es = MockEventSource.instances.find((x) =>
      x.url.endsWith("/api/channel/weixin/login"),
    )!;
    unmount();
    expect(es.closed).toBe(true);
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
