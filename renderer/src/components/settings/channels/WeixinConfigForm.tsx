import { Check, Copy, RefreshCw, Trash2, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { channelApi } from "@/lib/channelApi";
import type {
  ChannelPairing,
  ChannelPluginStatus,
  ChannelUser,
} from "@/types/channel";
import type { ModelProfile } from "@/window";

type LoginState = "idle" | "loading_qr" | "showing_qr" | "scanned" | "connected";

interface AssistantOption {
  id: string;
  name: string;
}

function remainingMinutes(expiresAt: number): number {
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000 / 60));
}

export default function WeixinConfigForm({
  pluginStatus,
  onStatusChange,
  onToast,
}: {
  pluginStatus: ChannelPluginStatus | null;
  onStatusChange: (status: ChannelPluginStatus | null) => void;
  onToast: (message: string) => void;
}) {
  const [loginState, setLoginState] = useState<LoginState>(
    pluginStatus?.has_token && pluginStatus?.enabled ? "connected" : "idle",
  );
  const [qrcodeData, setQrcodeData] = useState<string | null>(null);
  const closeLoginRef = useRef<(() => void) | null>(null);
  const [pairings, setPairings] = useState<ChannelPairing[]>([]);
  const [users, setUsers] = useState<ChannelUser[]>([]);
  const [assistants, setAssistants] = useState<AssistantOption[]>([]);
  const [assistantId, setAssistantId] = useState("");
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [modelId, setModelId] = useState("");

  useEffect(() => {
    return () => {
      closeLoginRef.current?.();
      closeLoginRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (pluginStatus?.has_token && pluginStatus?.enabled && loginState === "idle") {
      setLoginState("connected");
    }
  }, [pluginStatus, loginState]);

  const loadPairings = useCallback(async () => {
    const list = await channelApi.getPairings();
    setPairings(list.filter((p) => p.platform_type === "weixin"));
  }, []);

  const loadUsers = useCallback(async () => {
    const list = await channelApi.getUsers();
    setUsers(list.filter((u) => u.platform_type === "weixin"));
  }, []);

  useEffect(() => {
    void loadPairings().catch(() => undefined);
    void loadUsers().catch(() => undefined);
  }, [loadPairings, loadUsers]);

  useEffect(() => {
    void (async () => {
      try {
        const backendUrl = await window.api.getBackendUrl();
        if (!backendUrl) return;
        const [asstRes, saved, modelState] = await Promise.all([
          fetch(`${backendUrl.replace(/\/$/, "")}/api/assistants`).then((r) => r.json()),
          channelApi.getSettings("weixin"),
          window.api.getModels?.() ?? Promise.resolve({ profiles: [], activeId: null }),
        ]);
        const list = Array.isArray(asstRes.assistants)
          ? (asstRes.assistants as AssistantOption[])
          : [];
        setAssistants(list);
        setAssistantId(saved.assistant?.assistant_id ?? "");
        setModels(modelState.profiles ?? []);
        setModelId(saved.default_model?.id || modelState.activeId || "");
      } catch {
        // ignore
      }
    })();
  }, []);

  useEffect(() => {
    return channelApi.subscribe((ev) => {
      if (ev.type === "channel.pairing-requested") {
        const p = ev.payload as unknown as ChannelPairing;
        if (p.platform_type !== "weixin") return;
        setPairings((prev) => (prev.some((x) => x.code === p.code) ? prev : [p, ...prev]));
      }
      if (ev.type === "channel.user-authorized") {
        const u = ev.payload as unknown as ChannelUser;
        if (u.platform_type !== "weixin") return;
        setUsers((prev) => (prev.some((x) => x.id === u.id) ? prev : [u, ...prev]));
        setPairings((prev) => prev.filter((x) => x.platform_user_id !== u.platform_user_id));
      }
      if (ev.type === "channel.plugin-status-changed") {
        const pluginId = String(ev.payload.plugin_id ?? "");
        const status = ev.payload.status as ChannelPluginStatus | undefined;
        if (pluginId === "weixin" && status) onStatusChange(status);
      }
    });
  }, [onStatusChange]);

  async function enableWithCreds(accountId: string, botToken: string, baseUrl?: string) {
    if (window.api?.setKey) {
      await window.api.setKey("weixin:account_id", accountId);
      await window.api.setKey("weixin:bot_token", botToken);
      if (baseUrl) await window.api.setKey("weixin:base_url", baseUrl);
    }
    const credentials: Record<string, unknown> = {
      account_id: accountId,
      bot_token: botToken,
    };
    await channelApi.enablePlugin("weixin", { credentials });
    onToast("微信频道已启用");
    const plugins = await channelApi.getPlugins();
    onStatusChange(plugins.find((p) => p.plugin_id === "weixin") ?? null);
    setLoginState("connected");
  }

  async function handleLogin() {
    closeLoginRef.current?.();
    setLoginState("loading_qr");
    setQrcodeData(null);
    try {
      closeLoginRef.current = await channelApi.loginWeixin({
        onQr: (data) => {
          setQrcodeData(data);
          setLoginState("showing_qr");
        },
        onScanned: () => setLoginState("scanned"),
        onDone: (data) => {
          void enableWithCreds(data.accountId, data.botToken, data.baseUrl).catch((err: unknown) => {
            onToast(err instanceof Error ? err.message : "启用微信插件失败");
            setLoginState("idle");
            setQrcodeData(null);
          });
        },
        onError: (message) => {
          const lower = message.toLowerCase();
          if (lower.includes("expired") || lower.includes("too many")) {
            onToast("二维码已过期，请重试");
          } else if (message) {
            onToast("微信登录失败");
          }
          setLoginState("idle");
          setQrcodeData(null);
        },
      });
    } catch (err) {
      onToast(err instanceof Error ? err.message : "微信登录失败");
      setLoginState("idle");
    }
  }

  async function handleDisconnect() {
    try {
      await channelApi.disablePlugin("weixin");
      onToast("微信频道已禁用");
      onStatusChange(null);
      setLoginState("idle");
      setQrcodeData(null);
    } catch (err) {
      onToast(err instanceof Error ? err.message : "断开连接失败");
    }
  }

  const connected = loginState === "connected" || Boolean(pluginStatus?.has_token && pluginStatus?.enabled);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-body-sm font-bold text-ds-text-neutral-default-default">账号 ID</div>
          <div className="mt-0.5 text-[12px] text-ds-text-neutral-muted-default">
            {connected ? pluginStatus?.bot_username || "已连接" : "请用微信扫描二维码"}
          </div>
        </div>
        {connected ? (
          <div className="flex items-center gap-2">
            <Check size={16} className="text-green-600" />
            <span className="text-[14px]">已连接</span>
            <Button type="button" size="sm" variant="secondary" onClick={() => void handleDisconnect()}>
              断开连接
            </Button>
          </div>
        ) : loginState === "showing_qr" || loginState === "scanned" ? (
          <div className="flex flex-col items-center gap-2">
            {qrcodeData ? <QRCodeSVG value={qrcodeData} size={160} /> : null}
            <span className="text-[13px] text-ds-text-neutral-muted-default">
              {loginState === "scanned" ? "已扫码，等待确认..." : "请用微信扫描二维码"}
            </span>
          </div>
        ) : (
          <Button
            type="button"
            disabled={loginState === "loading_qr"}
            onClick={() => void handleLogin()}
          >
            {loginState === "loading_qr" ? "加载中…" : "扫码登录"}
          </Button>
        )}
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-body-sm font-bold text-ds-text-neutral-default-default">助手</span>
        <span className="text-[12px] text-ds-text-neutral-muted-default">用于与 Channel 进行对话</span>
        <select
          className="h-10 rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default px-3 text-body-sm"
          value={assistantId}
          aria-label="微信助手"
          onChange={(e) => {
            const id = e.target.value;
            setAssistantId(id);
            if (id) void channelApi.setAssistant("weixin", id).catch(() => undefined);
          }}
        >
          <option value="">默认助手</option>
          {assistants.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-body-sm font-bold text-ds-text-neutral-default-default">对话模型</span>
        <span className="text-[12px] text-ds-text-neutral-muted-default">用于通过此助手发起的微信对话</span>
        <select
          className="h-10 rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default px-3 text-body-sm"
          value={modelId}
          aria-label="微信默认模型"
          onChange={(e) => {
            const id = e.target.value;
            setModelId(id);
            const profile = models.find((m) => m.id === id);
            if (profile) {
              void channelApi.setDefaultModel("weixin", profile.id, profile.model).catch(() => undefined);
            }
          }}
        >
          <option value="">跟随当前模型</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.model})
            </option>
          ))}
        </select>
      </label>

      {pluginStatus?.connected && users.length === 0 ? (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <h3 className="m-0 mb-2 text-[14px] font-medium">下一步操作</h3>
          <div className="space-y-2 text-[14px]">
            <p className="m-0">
              <strong>1.</strong> 在微信中找到并给你的机器人发送任意消息
            </p>
            <p className="m-0">
              <strong>2.</strong> 配对请求会显示在下方，点击「批准」授权用户
            </p>
            <p className="m-0">
              <strong>3.</strong> 授权成功后，即可通过微信与 AI 助手对话
            </p>
          </div>
        </div>
      ) : null}

      {pluginStatus?.connected ? (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="m-0 text-[14px] font-medium">待批准的配对请求</h3>
            <Button type="button" size="sm" variant="ghost" onClick={() => void loadPairings()}>
              <RefreshCw size={14} />
              刷新
            </Button>
          </div>
          {pairings.length === 0 ? (
            <p className="text-[13px] text-ds-text-neutral-muted-default">暂无待批准的配对请求</p>
          ) : (
            <div className="flex flex-col gap-2">
              {pairings.map((p) => (
                <div
                  key={p.code}
                  className="flex items-center justify-between rounded-lg bg-ds-bg-neutral-subtle-default p-3"
                >
                  <div>
                    <div className="flex items-center gap-2 text-[14px] font-medium">
                      {p.display_name || p.platform_user_id}
                      <button
                        type="button"
                        aria-label="复制配对码"
                        onClick={() => {
                          void navigator.clipboard?.writeText(p.code);
                          onToast("已复制");
                        }}
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                    <div className="mt-1 text-[12px] text-ds-text-neutral-muted-default">
                      配对码：<code>{p.code}</code>
                      <span className="mx-2">|</span>
                      剩余 {remainingMinutes(p.expires_at)} 分钟
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() =>
                        void channelApi.approvePairing(p.code).then(() => {
                          onToast("配对已批准");
                          return Promise.all([loadPairings(), loadUsers()]);
                        })
                      }
                    >
                      <Check size={14} />
                      批准
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        void channelApi.rejectPairing(p.code).then(() => {
                          onToast("配对已拒绝");
                          return loadPairings();
                        })
                      }
                    >
                      <X size={14} />
                      拒绝
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {users.length > 0 ? (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="m-0 text-[14px] font-medium">已授权用户</h3>
            <Button type="button" size="sm" variant="ghost" onClick={() => void loadUsers()}>
              <RefreshCw size={14} />
              刷新
            </Button>
          </div>
          <div className="flex flex-col gap-2">
            {users.map((u) => (
              <div
                key={u.id}
                className="flex items-center justify-between rounded-lg bg-ds-bg-neutral-subtle-default p-3"
              >
                <div>
                  <div className="text-[14px] font-medium">{u.display_name || u.platform_user_id}</div>
                  <div className="mt-1 text-[12px] text-ds-text-neutral-muted-default">
                    授权时间：{new Date(u.authorized_at).toLocaleString()}
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label="撤销访问权限"
                  onClick={() =>
                    void channelApi.revokeUser(u.id).then(() => {
                      onToast("已撤销用户访问权限");
                      return loadUsers();
                    })
                  }
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
