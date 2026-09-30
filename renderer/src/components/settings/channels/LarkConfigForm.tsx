import { Check, Copy, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { SettingsField } from "@/components/settings/SettingsField";
import { channelApi } from "@/lib/channelApi";
import { cn } from "@/lib/utils";
import type {
  ChannelPairing,
  ChannelPluginStatus,
  ChannelUser,
} from "@/types/channel";
import type { ModelProfile } from "@/window";

const LARK_DEV_DOCS_URL =
  "https://open.feishu.cn/document/develop-an-echo-bot/introduction";

interface AssistantOption {
  id: string;
  name: string;
}

function remainingMinutes(expiresAt: number): number {
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000 / 60));
}

export default function LarkConfigForm({
  pluginStatus,
  onStatusChange,
  onToast,
}: {
  pluginStatus: ChannelPluginStatus | null;
  onStatusChange: (status: ChannelPluginStatus | null) => void;
  onToast: (message: string) => void;
}) {
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [encryptKey, setEncryptKey] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [showOptional, setShowOptional] = useState(false);
  const [secretSaved, setSecretSaved] = useState(false);
  const [encryptSaved, setEncryptSaved] = useState(false);
  const [tokenSaved, setTokenSaved] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [localStatus, setLocalStatus] = useState("");
  const appIdRef = useRef<HTMLInputElement>(null);
  const appSecretRef = useRef<HTMLInputElement>(null);
  const encryptKeyRef = useRef<HTMLInputElement>(null);
  const verificationTokenRef = useRef<HTMLInputElement>(null);
  const [pairings, setPairings] = useState<ChannelPairing[]>([]);
  const [users, setUsers] = useState<ChannelUser[]>([]);
  const [assistants, setAssistants] = useState<AssistantOption[]>([]);
  const [assistantId, setAssistantId] = useState("");
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [modelId, setModelId] = useState("");

  const hasExistingUsers = users.length > 0;
  const credsLocked = hasExistingUsers;

  const loadPairings = useCallback(async () => {
    const list = await channelApi.getPairings();
    setPairings(list.filter((p) => p.platform_type === "lark"));
  }, []);

  const loadUsers = useCallback(async () => {
    const list = await channelApi.getUsers();
    setUsers(list.filter((u) => u.platform_type === "lark"));
  }, []);

  useEffect(() => {
    void loadPairings().catch(() => undefined);
    void loadUsers().catch(() => undefined);
  }, [loadPairings, loadUsers]);

  useEffect(() => {
    if (!window.api?.getKey) return;
    void (async () => {
      const [id, secret, token, enc] = await Promise.all([
        window.api.getKey("lark:app_id"),
        window.api.getKey("lark:app_secret"),
        window.api.getKey("lark:verify_token"),
        window.api.getKey("lark:encrypt_key"),
      ]);
      if (id) setAppId(id);
      if (secret) setSecretSaved(true);
      if (token) setTokenSaved(true);
      if (enc) setEncryptSaved(true);
    })();
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const backendUrl = await window.api.getBackendUrl();
        if (!backendUrl) return;
        const [asstRes, saved, modelState] = await Promise.all([
          fetch(`${backendUrl.replace(/\/$/, "")}/api/assistants`).then((r) =>
            r.json(),
          ),
          channelApi.getSettings("lark"),
          window.api.getModels?.() ?? Promise.resolve({ profiles: [], activeId: null }),
        ]);
        const list = Array.isArray(asstRes.assistants)
          ? (asstRes.assistants as AssistantOption[])
          : [];
        setAssistants(list);
        const savedId = saved.assistant?.assistant_id ?? "";
        setAssistantId(savedId);
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
        if (p.platform_type !== "lark") return;
        setPairings((prev) =>
          prev.some((x) => x.code === p.code) ? prev : [p, ...prev],
        );
      }
      if (ev.type === "channel.user-authorized") {
        const u = ev.payload as unknown as ChannelUser;
        if (u.platform_type !== "lark") return;
        setUsers((prev) => (prev.some((x) => x.id === u.id) ? prev : [u, ...prev]));
        setPairings((prev) =>
          prev.filter((x) => x.platform_user_id !== u.platform_user_id),
        );
      }
      if (ev.type === "channel.plugin-status-changed") {
        const pluginId = String(ev.payload.plugin_id ?? "");
        const status = ev.payload.status as ChannelPluginStatus | undefined;
        if (pluginId === "lark" && status) onStatusChange(status);
      }
    });
  }, [onStatusChange]);

  async function persistKeys(creds: {
    app_id: string;
    app_secret: string;
    encrypt_key?: string;
    verification_token?: string;
  }) {
    if (!window.api?.setKey) return;
    await window.api.setKey("lark:app_id", creds.app_id);
    if (creds.app_secret) {
      await window.api.setKey("lark:app_secret", creds.app_secret);
      setSecretSaved(true);
      setAppSecret("");
    }
    if (creds.verification_token) {
      await window.api.setKey("lark:verify_token", creds.verification_token);
      setTokenSaved(true);
      setVerificationToken("");
    }
    if (creds.encrypt_key) {
      await window.api.setKey("lark:encrypt_key", creds.encrypt_key);
      setEncryptSaved(true);
      setEncryptKey("");
    }
  }

  async function resolveSecret(): Promise<string> {
    const typed = appSecret.trim() || appSecretRef.current?.value.trim() || "";
    if (typed) return typed;
    if (!window.api?.getKey) return "";
    return (await window.api.getKey("lark:app_secret"))?.trim() || "";
  }

  function notify(message: string) {
    setLocalStatus(message);
    onToast(message);
  }

  async function handleTestConnect() {
    const resolvedAppId = appId.trim() || appIdRef.current?.value.trim() || "";
    const resolvedSecret = await resolveSecret();
    if (!resolvedAppId || !resolvedSecret) {
      notify("请输入 App ID 和 App Secret");
      return;
    }
    setTestLoading(true);
    setLocalStatus("正在测试飞书凭证…");
    try {
      const credentials = {
        app_id: resolvedAppId,
        app_secret: resolvedSecret,
        encrypt_key:
          encryptKey.trim() || encryptKeyRef.current?.value.trim() || undefined,
        verification_token:
          verificationToken.trim() ||
          verificationTokenRef.current?.value.trim() ||
          undefined,
      };
      const result = await channelApi.testPlugin("lark", {
        app_id: credentials.app_id,
        app_secret: credentials.app_secret,
      });
      if (!result.success) {
        notify(result.error || "连接失败");
        return;
      }
      notify("已连接到飞书 API，正在启用长连接…");
      await persistKeys(credentials);
      await channelApi.enablePlugin("lark", { credentials });
      notify("飞书机器人已启用");
      const plugins = await channelApi.getPlugins();
      onStatusChange(plugins.find((p) => p.plugin_id === "lark") ?? null);
    } catch (err) {
      notify(err instanceof Error ? err.message : "启用飞书插件失败");
    } finally {
      setTestLoading(false);
    }
  }

  const connectionKind = useMemo(() => {
    if (pluginStatus?.connected) return "connected";
    if (pluginStatus?.error || pluginStatus?.status === "error") return "error";
    return "connecting";
  }, [pluginStatus]);

  const showTestButton = !hasExistingUsers && !pluginStatus?.connected;

  return (
    <div className="flex flex-col gap-5">
      <SettingsField
        ref={appIdRef}
        title="App ID"
        aria-label="飞书 App ID"
        placeholder={pluginStatus?.has_token ? "••••••••••••••••" : "cli_xxxxxxxxxx"}
        value={appId}
        disabled={credsLocked}
        autoComplete="off"
        note={
          <span>
            <a
              className="text-ds-text-brand-default-default underline"
              href={LARK_DEV_DOCS_URL}
              target="_blank"
              rel="noreferrer"
            >
              飞书开放平台开发者后台
            </a>{" "}
            获取 App ID
          </span>
        }
        onChange={(e) => setAppId(e.target.value)}
      />
      <SettingsField
        ref={appSecretRef}
        title="App Secret"
        aria-label="飞书 App Secret"
        type="password"
        autoComplete="new-password"
        disabled={credsLocked}
        value={appSecret}
        placeholder={
          secretSaved || pluginStatus?.has_token
            ? "已保存，留空则保持不变"
            : "xxxxxxxxxxxxxxxxxx"
        }
        note={
          <span>
            <a
              className="text-ds-text-brand-default-default underline"
              href={LARK_DEV_DOCS_URL}
              target="_blank"
              rel="noreferrer"
            >
              飞书开放平台开发者后台
            </a>{" "}
            获取 App Secret
          </span>
        }
        onChange={(e) => setAppSecret(e.target.value)}
      />

      <button
        type="button"
        className="self-start text-[12px] text-ds-text-neutral-muted-default"
        onClick={() => setShowOptional((v) => !v)}
      >
        {showOptional ? "隐藏可选配置" : "显示可选配置"}
      </button>

      {showOptional ? (
        <>
          <SettingsField
            ref={encryptKeyRef}
            title="Encrypt Key"
            aria-label="飞书 Encrypt Key"
            type="password"
            disabled={credsLocked}
            value={encryptKey}
            placeholder={encryptSaved ? "已保存，留空则保持不变" : "可选"}
            note="可选：用于事件加密（来自事件订阅配置）"
            onChange={(e) => setEncryptKey(e.target.value)}
          />
          <SettingsField
            ref={verificationTokenRef}
            title="Verification Token"
            aria-label="飞书 Verification Token"
            type="password"
            disabled={credsLocked}
            value={verificationToken}
            placeholder={tokenSaved ? "已保存，留空则保持不变" : "可选"}
            note="可选：用于事件验证（来自事件订阅配置）"
            onChange={(e) => setVerificationToken(e.target.value)}
          />
        </>
      ) : null}

      {showTestButton ? (
        <div className="flex flex-col items-end gap-2">
          {localStatus ? (
            <p className="w-full text-right text-[13px] text-ds-text-neutral-default-default" role="status">
              {localStatus}
            </p>
          ) : null}
          <Button
            type="button"
            disabled={testLoading}
            onClick={() => void handleTestConnect()}
          >
            {testLoading ? "连接中…" : "测试并连接"}
          </Button>
        </div>
      ) : null}

      <label className="flex flex-col gap-1.5">
        <span className="text-body-sm font-bold text-ds-text-neutral-default-default">
          助手
        </span>
        <span className="text-[12px] text-ds-text-neutral-muted-default">
          用于与 Channel 进行对话
        </span>
        <select
          className="h-10 rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default px-3 text-body-sm"
          value={assistantId}
          aria-label="飞书助手"
          onChange={(e) => {
            const id = e.target.value;
            setAssistantId(id);
            if (id) void channelApi.setAssistant("lark", id).catch(() => undefined);
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
        <span className="text-body-sm font-bold text-ds-text-neutral-default-default">
          对话模型
        </span>
        <span className="text-[12px] text-ds-text-neutral-muted-default">
          用于通过此助手发起的 Lark 对话
        </span>
        <select
          className="h-10 rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default px-3 text-body-sm"
          value={modelId}
          aria-label="飞书默认模型"
          onChange={(e) => {
            const id = e.target.value;
            setModelId(id);
            const profile = models.find((m) => m.id === id);
            if (profile) {
              void channelApi
                .setDefaultModel("lark", profile.id, profile.model)
                .catch(() => undefined);
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

      {pluginStatus?.enabled && !hasExistingUsers ? (
        <div
          className={cn(
            "rounded-xl border p-4",
            connectionKind === "connected"
              ? "border-green-200 bg-green-50"
              : connectionKind === "error"
                ? "border-red-200 bg-red-50"
                : "border-yellow-200 bg-yellow-50",
          )}
        >
          <div className="mb-3 flex items-center justify-between">
            <h3 className="m-0 text-[14px] font-medium">连接状态</h3>
            <span className="rounded px-2 py-0.5 text-[12px]">
              {connectionKind === "connected"
                ? "✅ 已连接"
                : connectionKind === "error"
                  ? "❌ 错误"
                  : "⏳ 连接中..."}
            </span>
          </div>
          {connectionKind === "connected" ? (
            <div className="space-y-2 text-[14px] text-ds-text-neutral-default-default">
              <p className="m-0 font-medium">下一步操作：</p>
              <p className="m-0">
                <strong>1.</strong> 打开飞书/Lark 找到你的机器人应用
              </p>
              <p className="m-0">
                <strong>2.</strong> 发送任意消息开始配对
              </p>
              <p className="m-0">
                <strong>3.</strong> 配对请求会显示在下方，点击「批准」授权用户
              </p>
              <p className="m-0">
                <strong>4.</strong> 授权成功后，你可以通过飞书与 AI 助手聊天！
              </p>
            </div>
          ) : connectionKind === "error" ? (
            <p className="m-0 text-[14px] text-red-600">
              {String(pluginStatus.error || "连接失败")}
            </p>
          ) : (
            <p className="m-0 text-[14px]">WebSocket 连接正在建立，请稍候...</p>
          )}
        </div>
      ) : null}

      {pluginStatus?.enabled && !hasExistingUsers ? (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="m-0 text-[14px] font-medium">待批准的配对请求</h3>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => void loadPairings()}
            >
              <RefreshCw size={14} />
              刷新
            </Button>
          </div>
          {pairings.length === 0 ? (
            <p className="text-[13px] text-ds-text-neutral-muted-default">
              暂无待批准的配对请求
            </p>
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

      {hasExistingUsers ? (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="m-0 text-[14px] font-medium">已授权用户</h3>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => void loadUsers()}
            >
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
                  <div className="text-[14px] font-medium">
                    {u.display_name || u.platform_user_id}
                  </div>
                  <div className="mt-1 text-[12px] text-ds-text-neutral-muted-default">
                    平台：{u.platform_type}
                    <span className="mx-2">|</span>
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
