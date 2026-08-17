import {
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Key,
  Loader2,
  RefreshCw,
  Server,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ConfigModelCard,
  type ConfigCardRingStatus,
} from "@/components/settings/ConfigModelCard";
import { SettingsField } from "@/components/settings/SettingsField";
import {
  BYOK_PRESETS,
  LOCAL_PRESETS,
  findPreset,
  modelListUrl,
  profileForPreset as matchProfile,
  type ModelPreset,
} from "@/lib/modelPresets";
import {
  getModelImage,
  isDarkAppearance,
  needsInvertModelImage,
} from "@/lib/modelProviderImages";
import { cn } from "@/lib/utils";
import type { ModelProfile, ModelsState } from "@/window";

type SidebarTab = `byok-${string}` | `local-${string}`;

function profileForPreset(
  models: ModelsState,
  preset: ModelPreset,
): ModelProfile | undefined {
  return matchProfile(models.profiles, preset) as ModelProfile | undefined;
}

function StatusDot({
  tone,
}: {
  tone: "success" | "error" | "muted" | null;
}) {
  if (!tone) {
    return (
      <div className="m-1 h-2 w-2 shrink-0 rounded-full bg-ds-text-neutral-default-default opacity-10" />
    );
  }
  return (
    <div
      className={cn(
        "m-1 h-2 w-2 shrink-0 rounded-full",
        tone === "success" && "bg-ds-text-success-default-default",
        tone === "error" && "bg-ds-text-error-default-default",
        tone === "muted" && "bg-ds-text-neutral-default-default opacity-10",
      )}
    />
  );
}

function dotToneFor(
  profile: ModelProfile | undefined,
): "success" | "error" | "muted" | null {
  if (!profile) return null;
  if (profile.isValid === false) return "error";
  if (profile.isValid) return "success";
  return "muted";
}

export default function ModelsPanel({ embedded = false }: { embedded?: boolean }) {
  const [models, setModels] = useState<ModelsState>({ profiles: [], activeId: null });
  const [selectedTab, setSelectedTab] = useState<SidebarTab>("byok-anthropic");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.anthropic.com");
  const [modelId, setModelId] = useState("claude-sonnet-4-20250514");
  const [editId, setEditId] = useState<string | null>(null);
  const [ring, setRing] = useState<ConfigCardRingStatus>("idle");
  const [status, setStatus] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [busy, setBusy] = useState(false);
  const [remoteModels, setRemoteModels] = useState<string[]>([]);
  const [listing, setListing] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [byokCollapsed, setByokCollapsed] = useState(false);
  const [localCollapsed, setLocalCollapsed] = useState(false);
  const keyLoadSeq = useRef(0);
  const appearance = isDarkAppearance() ? "dark" : "light";

  const loadApiKey = useCallback((profileId: string | null | undefined) => {
    const seq = ++keyLoadSeq.current;
    if (!profileId || !window.api?.getKey) {
      setApiKey("");
      return;
    }
    void window.api.getKey(`model:${profileId}`).then((key) => {
      if (seq !== keyLoadSeq.current) return;
      setApiKey(key ?? "");
    });
  }, []);

  const refresh = useCallback(() => {
    if (!window.api?.getModels) return;
    void window.api.getModels().then(setModels).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Backfill key when the active profile id changes (tab switch / first load).
  useEffect(() => {
    const presetId = selectedTab.startsWith("local-")
      ? selectedTab.slice(6)
      : selectedTab.startsWith("byok-")
        ? selectedTab.slice(5)
        : null;
    const preset = findPreset(presetId);
    const existing = preset ? profileForPreset(models, preset) : undefined;
    if (existing) {
      setEditId((prev) => (prev === existing.id ? prev : existing.id));
      loadApiKey(existing.id);
    } else {
      loadApiKey(null);
    }
  }, [models.profiles, selectedTab, loadApiKey]);

  const selectedPreset = useMemo(() => {
    if (selectedTab.startsWith("byok-")) return findPreset(selectedTab.slice(5));
    if (selectedTab.startsWith("local-")) return findPreset(selectedTab.slice(6));
    return undefined;
  }, [selectedTab]);

  const editingProfile = useMemo(() => {
    if (editId) return models.profiles.find((p) => p.id === editId);
    if (selectedPreset) return profileForPreset(models, selectedPreset);
    return undefined;
  }, [editId, models, selectedPreset]);

  const isConfigured = !!editingProfile;
  const isDefault = !!(editId && models.activeId === editId) ||
    !!(editingProfile && models.activeId === editingProfile.id);

  function applyPreset(preset: ModelPreset, existing?: ModelProfile) {
    setSelectedTab(
      (preset.category === "local" ? `local-${preset.id}` : `byok-${preset.id}`) as SidebarTab,
    );
    setEditId(existing?.id ?? null);
    setBaseUrl(existing?.baseUrl ?? preset.defaultHost);
    setModelId(existing?.model ?? preset.defaultModel);
    setShowApiKey(false);
    setRemoteModels([]);
    setRing(existing?.isValid ? "success" : existing?.isValid === false ? "error" : "idle");
    setStatus("");
    setFieldError("");
    loadApiKey(existing?.id);
  }

  async function refreshModelList() {
    if (!selectedPreset?.parseModels) {
      setStatus("当前预设不支持拉取模型列表");
      return;
    }
    const url = modelListUrl(baseUrl.trim() || selectedPreset.defaultHost, selectedPreset);
    if (!url) {
      setStatus("无法解析模型列表地址");
      return;
    }
    setListing(true);
    setStatus("");
    try {
      const headers: Record<string, string> = {};
      if (apiKey.trim()) headers.Authorization = `Bearer ${apiKey.trim()}`;
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: unknown = await res.json();
      const list = selectedPreset.parseModels(data);
      setRemoteModels(list);
      if (!list.length) setStatus("列表为空");
    } catch (err) {
      setFieldError(`刷新失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setListing(false);
    }
  }

  async function validateAndSave(activate: boolean) {
    const preset = selectedPreset;
    const provider = preset?.provider ?? editingProfile?.provider;
    if (!provider || !preset) {
      setFieldError("请选择厂商预设");
      return;
    }
    if (!modelId.trim()) {
      setFieldError("请填写模型类型");
      return;
    }
    const needsKey =
      preset.requiresApiKey !== false &&
      provider !== "ollama" &&
      provider !== "lmstudio" &&
      provider !== "vllm";
    if (needsKey && !apiKey.trim() && !editId) {
      setFieldError("请填写 API 密钥");
      setRing("error");
      return;
    }

    setBusy(true);
    setRing("configuring");
    setStatus("");
    setFieldError("");
    try {
      let keyForProbe = apiKey.trim();
      if (!keyForProbe && editId && window.api?.getKey) {
        keyForProbe = (await window.api.getKey(`model:${editId}`))?.trim() ?? "";
      }
      if (needsKey && !keyForProbe) {
        setRing("error");
        setFieldError("缺少 API 密钥，请重新填写");
        setBusy(false);
        return;
      }

      let result = { ok: false, error: "无法校验", latency_ms: 0 as number | undefined };
      if (window.api?.validateModel) {
        result = await window.api.validateModel({
          provider,
          model: modelId.trim(),
          apiKey: keyForProbe || undefined,
          baseUrl: baseUrl.trim() || undefined,
        });
      } else {
        const backendUrl = await window.api?.getBackendUrl?.();
        if (!backendUrl) throw new Error("后端未连接，且无本地探活");
        const res = await fetch(`${backendUrl}/api/model/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: provider === "anthropic" ? "anthropic" : "openai_compat",
            model: modelId.trim(),
            api_key: keyForProbe,
            base_url: baseUrl.trim() || undefined,
          }),
        });
        result = (await res.json()) as typeof result;
      }

      if (!result.ok) {
        setRing("error");
        setFieldError(result.error || "校验失败");
        return;
      }

      const next = await window.api.upsertModel({
        id: editId ?? undefined,
        name: preset.name,
        provider,
        model: modelId.trim(),
        baseUrl: baseUrl.trim() || undefined,
        apiKey: apiKey.trim() || undefined,
        activate,
        isValid: true,
        lastValidatedAt: new Date().toISOString(),
        category: preset.category,
        presetId: preset.id,
      });
      setModels(next);
      const saved =
        next.profiles.find((p) => p.id === editId) ??
        next.profiles.find((p) => p.presetId === preset.id && p.model === modelId.trim());
      if (saved) {
        setEditId(saved.id);
        // Keep typed key in the field; if we only validated with stored key, reload it.
        if (!apiKey.trim()) loadApiKey(saved.id);
      }
      setRing("success");
      setStatus(
        activate
          ? `已保存并启用${result.latency_ms != null ? `（${result.latency_ms}ms）` : ""}`
          : `已保存${result.latency_ms != null ? `（${result.latency_ms}ms）` : ""}`,
      );
    } catch (err) {
      setRing("error");
      setFieldError(`失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function setAsDefault() {
    const id = editId ?? editingProfile?.id;
    if (!id) return;
    setStatus("正在切换模型…");
    try {
      const next = await window.api.setActiveModel(id);
      setModels(next);
      setStatus("已设为默认");
    } catch (err) {
      setFieldError(`切换失败：${err instanceof Error ? err.message : String(err)}`);
    }
  }

  async function resetProfile() {
    const id = editId ?? editingProfile?.id;
    if (!id) {
      if (selectedPreset) applyPreset(selectedPreset);
      return;
    }
    const next = await window.api.removeModel(id);
    setModels(next);
    if (selectedPreset) applyPreset(selectedPreset);
    setStatus("已重置");
  }

  function renderSidebarItem(
    tabId: SidebarTab,
    label: string,
    logoId: string | null,
    isActive: boolean,
    tone: "success" | "error" | "muted" | null,
    fallback: "key" | "server",
  ) {
    const modelImage = getModelImage(logoId);
    const FallbackIcon = fallback === "server" ? Server : Key;
    return (
      <button
        key={tabId}
        type="button"
        onClick={() => {
          const preset = findPreset(
            tabId.startsWith("local-") ? tabId.slice(6) : tabId.slice(5),
          );
          if (preset) applyPreset(preset, profileForPreset(models, preset));
        }}
        className={cn(
          "flex w-full items-center justify-between rounded-xl px-3 py-2 transition-colors duration-200",
          isActive
            ? "bg-ds-bg-neutral-subtle-default hover:bg-ds-bg-neutral-subtle-default"
            : "bg-transparent hover:bg-ds-bg-neutral-subtle-default/70",
        )}
      >
        <div className="flex items-center justify-center gap-3">
          {modelImage ? (
            <img
              src={modelImage}
              alt={label}
              className="h-5 w-5"
              style={
                needsInvertModelImage(logoId, appearance)
                  ? { filter: "invert(1)" }
                  : undefined
              }
            />
          ) : (
            <span
              className={
                isActive
                  ? "text-ds-text-neutral-default-default"
                  : "text-ds-text-neutral-muted-default"
              }
            >
              <FallbackIcon className="h-5 w-5" />
            </span>
          )}
          <span
            className={cn(
              "text-body-sm font-medium",
              isActive
                ? "text-ds-text-neutral-default-default"
                : "text-ds-text-neutral-muted-default",
            )}
          >
            {label}
          </span>
        </div>
        <StatusDot tone={tone} />
      </button>
    );
  }

  const showKey = selectedPreset?.category !== "local";
  const displayName = selectedPreset?.name ?? "模型";

  const panel = (
    <div className="flex w-full flex-row items-start justify-between">
      {/* Sidebar — Eigent: w-[240px] rounded-2xl */}
      <div className="-ml-2 mr-4 h-full w-[240px] shrink-0 rounded-2xl bg-ds-bg-neutral-default-default">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <div className="px-3 py-2 text-body-sm font-bold text-ds-text-neutral-default-default">
              自定义模型
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex flex-col gap-1">
                <button
                  type="button"
                  onClick={() => setByokCollapsed((v) => !v)}
                  className="flex items-center justify-between rounded-lg bg-transparent px-3 py-2 transition-colors hover:bg-ds-bg-neutral-default-default"
                >
                  <div className="text-body-sm font-medium text-ds-text-neutral-muted-default">
                    自带密钥
                  </div>
                  {byokCollapsed ? (
                    <ChevronDown className="h-4 w-4 text-ds-text-neutral-muted-default" />
                  ) : (
                    <ChevronUp className="h-4 w-4 text-ds-text-neutral-muted-default" />
                  )}
                </button>
                <div
                  className={cn(
                    "overflow-hidden transition-opacity duration-[160ms] ease-[cubic-bezier(0.23,1,0.32,1)]",
                    byokCollapsed ? "max-h-0 opacity-0" : "max-h-[2000px] opacity-100",
                  )}
                >
                  {BYOK_PRESETS.map((preset) => {
                    const profile = profileForPreset(models, preset);
                    const tabId = `byok-${preset.id}` as SidebarTab;
                    return renderSidebarItem(
                      tabId,
                      preset.name,
                      preset.id,
                      selectedTab === tabId,
                      dotToneFor(profile),
                      "key",
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <button
              type="button"
              onClick={() => setLocalCollapsed((v) => !v)}
              className="flex items-center justify-between rounded-lg bg-transparent px-3 py-2 transition-colors hover:bg-ds-bg-neutral-default-default"
            >
              <div className="text-body-sm font-bold text-ds-text-neutral-default-default">
                本地模型
              </div>
              {localCollapsed ? (
                <ChevronDown className="h-4 w-4 text-ds-text-neutral-muted-default" />
              ) : (
                <ChevronUp className="h-4 w-4 text-ds-text-neutral-muted-default" />
              )}
            </button>
            <div
              className={cn(
                "overflow-hidden transition-opacity duration-[160ms] ease-[cubic-bezier(0.23,1,0.32,1)]",
                localCollapsed ? "max-h-0 opacity-0" : "max-h-[2000px] opacity-100",
              )}
            >
              {LOCAL_PRESETS.map((preset) => {
                const profile = profileForPreset(models, preset);
                const tabId = `local-${preset.id}` as SidebarTab;
                return renderSidebarItem(
                  tabId,
                  preset.name,
                  preset.id,
                  selectedTab === tabId,
                  dotToneFor(profile),
                  "server",
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Content card */}
      <div className="min-w-0 flex-1">
        <ConfigModelCard status={ring}>
          <div className="mx-6 mb-4 flex flex-col items-start justify-between border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default pb-4 pt-2">
            <div className="inline-flex items-center justify-between gap-2 self-stretch">
              <div className="text-body-base my-2 font-bold text-ds-text-neutral-default-default">
                {displayName}
              </div>
              <div className="flex items-center gap-2">
                {isDefault ? (
                  <Button
                    variant="primary"
                    size="xs"
                    disabled
                    className="!rounded-full !bg-ds-text-success-default-default !border-ds-text-success-default-default font-bold"
                  >
                    默认
                  </Button>
                ) : isConfigured ? (
                  <Button
                    variant="ghost"
                    size="xs"
                    className="!rounded-full !text-ds-text-neutral-muted-default font-bold"
                    onClick={() => void setAsDefault()}
                  >
                    设为默认
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="xs"
                    disabled
                    className="!rounded-full font-bold"
                  >
                    未配置
                  </Button>
                )}
                <StatusDot tone={dotToneFor(editingProfile)} />
              </div>
            </div>
            <div className="text-body-sm text-ds-text-neutral-muted-default">
              {selectedPreset?.category === "local"
                ? "连接本机 OpenAI 兼容端点；测试通过后保存。"
                : "填入 API Key 与模型类型，验证通过后才会保存。"}
            </div>
          </div>

          <div className="flex w-full flex-col items-center gap-4 px-6">
            {showKey && (
              <SettingsField
                title="API 密钥设置"
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setFieldError("");
                }}
                placeholder={`输入你的 ${displayName} Key`}
                aria-label="API 密钥"
                state={fieldError && !apiKey ? "error" : ring === "error" ? "error" : "default"}
                backIcon={showApiKey ? <Eye className="h-5 w-5" /> : <EyeOff className="h-5 w-5" />}
                onBackIconClick={() => setShowApiKey((v) => !v)}
              />
            )}

            <SettingsField
              title={selectedPreset?.category === "local" ? "模型端点 URL" : "API Host 设置"}
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setFieldError("");
              }}
              placeholder={`输入 ${displayName} URL`}
              aria-label="Base URL"
            />

            {selectedPreset?.parseModels ? (
              <div className="flex w-full flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <div className="text-body-sm font-bold text-ds-text-neutral-default-default">
                    模型类型设置
                  </div>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 text-body-sm text-ds-text-neutral-muted-default hover:text-ds-text-neutral-default-default"
                    onClick={() => void refreshModelList()}
                    disabled={listing}
                  >
                    {listing ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    刷新
                  </button>
                </div>
                {remoteModels.length > 0 ? (
                  <div className="relative flex h-10 items-center rounded-xl border border-solid border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default shadow-sm">
                    <select
                      className="h-full w-full cursor-pointer bg-transparent px-3 text-body-sm outline-none"
                      value={modelId}
                      onChange={(e) => setModelId(e.target.value)}
                      aria-label="模型 ID"
                    >
                      {!remoteModels.includes(modelId) && modelId && (
                        <option value={modelId}>{modelId}</option>
                      )}
                      {remoteModels.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <SettingsField
                    value={modelId}
                    onChange={(e) => setModelId(e.target.value)}
                    placeholder={`输入 ${displayName} 模型类型`}
                    aria-label="模型 ID"
                  />
                )}
              </div>
            ) : (
              <SettingsField
                title="模型类型设置"
                value={modelId}
                onChange={(e) => {
                  setModelId(e.target.value);
                  setFieldError("");
                }}
                placeholder={`输入 ${displayName} 模型类型`}
                aria-label="模型 ID"
                state={fieldError && !modelId.trim() ? "error" : "default"}
              />
            )}
          </div>

          <div className="flex justify-end gap-2 px-6 py-4">
            <Button
              variant="ghost"
              size="sm"
              className="font-medium"
              onClick={() => void resetProfile()}
            >
              重置
            </Button>
            <Button
              variant="primary"
              size="sm"
              className="font-bold"
              disabled={busy}
              onClick={() => void validateAndSave(true)}
            >
              {busy ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  配置中…
                </span>
              ) : (
                "保存"
              )}
            </Button>
          </div>

          {(fieldError || status) && (
            <p
              className={cn(
                "px-6 pb-4 text-body-sm",
                fieldError
                  ? "text-ds-text-error-default-default"
                  : "text-ds-text-neutral-muted-default",
              )}
            >
              {fieldError || status}
            </p>
          )}
        </ConfigModelCard>
      </div>
    </div>
  );

  if (embedded) {
    return (
      <div className="flex w-full flex-col items-start justify-between rounded-2xl bg-ds-bg-neutral-default-default px-3 py-2">
        <div className="text-body-base sticky top-[48px] z-10 mb-4 w-full border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default px-3 py-2 pb-2 font-bold text-ds-text-neutral-default-default">
          模型配置
        </div>
        <div className="w-full px-3">{panel}</div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col items-start justify-between">
      <div className="text-body-base mb-4 w-full border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default px-3 py-2 font-bold text-ds-text-neutral-default-default">
        模型配置
      </div>
      <div className="w-full px-3">{panel}</div>
    </div>
  );
}
