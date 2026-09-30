import { subscribeSSE, type SSEvent } from "@/api/sse";
import type {
  ChannelPairing,
  ChannelPluginStatus,
  ChannelSettings,
  ChannelUser,
} from "@/types/channel";

async function base(): Promise<string> {
  const url = await window.api.getBackendUrl();
  if (!url) throw new Error("后端未连接");
  return url.replace(/\/$/, "");
}

function isMissingRoute(status: number, data: { detail?: unknown }): boolean {
  return status === 404 && data.detail === "Not Found";
}

let backendRestart: Promise<string> | null = null;

function restartStaleBackend(): Promise<string> {
  if (!window.api?.restartBackend) {
    return Promise.reject(
      new Error("后端没有远程连接接口，请完全退出应用后重新打开"),
    );
  }
  if (!backendRestart) {
    backendRestart = window.api.restartBackend().finally(() => {
      backendRestart = null;
    });
  }
  return backendRestart;
}

function errorMessage(data: { detail?: unknown }, status: number): string {
  if (isMissingRoute(status, data)) {
    return "后端没有远程连接接口，请完全退出应用后重新打开";
  }
  const detail = data.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "msg" in item) {
        return String((item as { msg: unknown }).msg);
      }
      return "";
    });
    const joined = parts.filter(Boolean).join("；");
    if (joined) return joined;
  }
  return `HTTP ${status}`;
}

async function json<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const res = await fetch(`${await base()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const data = (await res.json().catch(() => ({}))) as T & { detail?: unknown };
  if (isMissingRoute(res.status, data) && !retried) {
    await restartStaleBackend();
    return json<T>(path, init, true);
  }
  if (!res.ok) {
    throw new Error(errorMessage(data, res.status));
  }
  return data;
}

export const channelApi = {
  getPlugins: () => json<ChannelPluginStatus[]>("/api/channel/plugins"),
  testPlugin: (pluginId: string, extra: Record<string, string>) =>
    json<{ success: boolean; bot_username?: string; error?: string }>(
      "/api/channel/plugins/test",
      {
        method: "POST",
        body: JSON.stringify({
          plugin_id: pluginId,
          token: "",
          extra_config: extra,
        }),
      },
    ),
  enablePlugin: (pluginId: string, config: Record<string, unknown> = {}) =>
    json<{ ok: boolean }>("/api/channel/plugins/enable", {
      method: "POST",
      body: JSON.stringify({ plugin_id: pluginId, config }),
    }),
  disablePlugin: (pluginId: string) =>
    json<{ ok: boolean }>("/api/channel/plugins/disable", {
      method: "POST",
      body: JSON.stringify({ plugin_id: pluginId }),
    }),
  getPairings: () => json<ChannelPairing[]>("/api/channel/pairings"),
  approvePairing: (code: string) =>
    json<{ ok: boolean }>("/api/channel/pairings/approve", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  rejectPairing: (code: string) =>
    json<{ ok: boolean }>("/api/channel/pairings/reject", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  getUsers: () => json<ChannelUser[]>("/api/channel/users"),
  revokeUser: (userId: string) =>
    json<{ ok: boolean }>("/api/channel/users/revoke", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  getSettings: (platform: string) =>
    json<ChannelSettings>(`/api/channel/settings/${encodeURIComponent(platform)}`),
  setAssistant: (platform: string, assistantId: string) =>
    json<{ ok: boolean }>(
      `/api/channel/settings/${encodeURIComponent(platform)}/assistant`,
      {
        method: "PUT",
        body: JSON.stringify({ assistant_id: assistantId }),
      },
    ),
  setDefaultModel: (platform: string, id: string, useModel: string) =>
    json<{ ok: boolean }>(
      `/api/channel/settings/${encodeURIComponent(platform)}/default-model`,
      {
        method: "PUT",
        body: JSON.stringify({ id, use_model: useModel }),
      },
    ),
  subscribe: (onEvent: (ev: SSEvent) => void): (() => void) => {
    let es: EventSource | null = null;
    let cancelled = false;
    void base().then((url) => {
      if (cancelled) return;
      es = subscribeSSE(`${url}/api/channel/stream`, onEvent);
    });
    return () => {
      cancelled = true;
      es?.close();
    };
  },
  loginWeixin: async (
    handlers: {
      onQr: (qrcodeData: string) => void;
      onScanned: () => void;
      onDone: (data: { accountId: string; botToken: string; baseUrl?: string }) => void;
      onError: (message: string) => void;
    },
  ): Promise<() => void> => {
    const url = await base();
    const es = new EventSource(`${url}/api/channel/weixin/login`);
    es.addEventListener("qr", (e: MessageEvent) => {
      try {
        const { qrcodeData } = JSON.parse(String(e.data)) as { qrcodeData: string };
        handlers.onQr(qrcodeData);
      } catch {
        handlers.onError("WeChat login failed");
      }
    });
    es.addEventListener("scanned", () => {
      handlers.onScanned();
    });
    es.addEventListener("done", (e: MessageEvent) => {
      es.close();
      try {
        const data = JSON.parse(String(e.data)) as {
          accountId: string;
          botToken: string;
          baseUrl?: string;
        };
        handlers.onDone(data);
      } catch {
        handlers.onError("WeChat login failed");
      }
    });
    es.addEventListener("error", (e: MessageEvent) => {
      es.close();
      let message = "";
      if (e.data) {
        try {
          message = String((JSON.parse(String(e.data)) as { message?: string }).message ?? "");
        } catch {
          message = "";
        }
      }
      handlers.onError(message);
    });
    es.onerror = () => {
      es.close();
      handlers.onError("");
    };
    return () => es.close();
  },
};
