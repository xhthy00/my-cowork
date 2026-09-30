import { Eye, EyeOff, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ConfigModelCard,
  type ConfigCardRingStatus,
} from "@/components/settings/ConfigModelCard";
import { SettingsField } from "@/components/settings/SettingsField";
import { getKnowledgeLogo } from "@/lib/knowledgeLogos";
import {
  KNOWLEDGE_SOURCE_GROUPS,
  KNOWLEDGE_SOURCES,
  knowledgeSourcesInGroup,
  type KnowledgeSourceId,
} from "@/lib/knowledgeSources";
import { cn } from "@/lib/utils";

const CLIENT_ACCOUNT = "ima:client_id";
const KEY_ACCOUNT = "ima:api_key";

async function backendBase(): Promise<string> {
  const url = await window.api?.getBackendUrl?.();
  if (!url) throw new Error("后端未连接");
  return url.replace(/\/$/, "");
}

async function readDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail != null) return JSON.stringify(body.detail);
  } catch {
    // ignore
  }
  return `请求失败 ${res.status}`;
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

export default function KnowledgeView() {
  const [selectedId, setSelectedId] = useState<KnowledgeSourceId>("ima");
  const [clientId, setClientId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [status, setStatus] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [ring, setRing] = useState<ConfigCardRingStatus>("idle");
  const [imaConfigured, setImaConfigured] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const selected =
    KNOWLEDGE_SOURCES.find((s) => s.id === selectedId) ?? KNOWLEDGE_SOURCES[0];

  const loadIma = useCallback(async () => {
    if (!window.api?.getKey) return;
    const [id, key] = await Promise.all([
      window.api.getKey(CLIENT_ACCOUNT),
      window.api.getKey(KEY_ACCOUNT),
    ]);
    const cid = id || "";
    const secret = key || "";
    setClientId(cid);
    setApiKey(secret);
    setImaConfigured(Boolean(cid && secret));
  }, []);

  useEffect(() => {
    void loadIma();
  }, [loadIma]);

  function selectSource(source: KnowledgeSource) {
    setSelectedId(source.id);
    setStatus("");
    setFieldError("");
    setShowKey(false);
    setRing(source.id === "ima" && imaConfigured ? "success" : "idle");
  }

  function imaDotTone(): "success" | "error" | "muted" | null {
    if (ring === "error" && selectedId === "ima") return "error";
    if (imaConfigured) return "success";
    return null;
  }

  async function testConnection(): Promise<boolean> {
    setTesting(true);
    setRing("configuring");
    try {
      const base = await backendBase();
      const res = await fetch(`${base}/api/ima/test`, { method: "POST" });
      if (!res.ok) throw new Error(await readDetail(res));
      const body = (await res.json()) as {
        sample_count?: number;
        empty?: boolean;
        names?: string[];
      };
      const n = body.sample_count ?? 0;
      setRing("success");
      setFieldError("");
      if (n > 0) {
        const preview = (body.names || []).slice(0, 3).join("、");
        setStatus(
          preview
            ? `连接成功，已检测到 ${n} 个知识库：${preview}`
            : `连接成功，已检测到 ${n} 个知识库。`,
        );
      } else {
        setStatus(
          "连接成功，但 OpenAPI 未列出任何知识库。请确认生成 API Key 的微信/QQ 与 IMA 客户端是同一账号；客户端里的「笔记」不会出现在知识库接口中。",
        );
      }
      return true;
    } catch (err) {
      setRing("error");
      setStatus("");
      setFieldError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    if (!window.api?.setKey) return;
    const id = clientId.trim();
    const key = apiKey.trim();
    if (!id || !key) {
      setRing("error");
      setFieldError("请填写 Client ID 和 API Key。");
      return;
    }
    setSaving(true);
    setRing("configuring");
    setFieldError("");
    setStatus("正在保存…");
    try {
      await Promise.all([
        window.api.setKey(CLIENT_ACCOUNT, id),
        window.api.setKey(KEY_ACCOUNT, key),
      ]);
      setImaConfigured(true);
      if (window.api.restartBackend) {
        await window.api.restartBackend();
      }
      setStatus("已保存。正在测试连接…");
      await testConnection();
    } catch (err) {
      setRing("error");
      setStatus("");
      setFieldError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  const busy = saving || testing;

  return (
    <div className="flex h-auto w-full flex-1 flex-col pb-12 pt-8">
      <div className="text-body-base mb-4 w-full border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default px-3 py-2 font-bold text-ds-text-neutral-default-default">
        知识库配置
      </div>
      <div className="flex w-full flex-row items-start justify-between px-3">
        <div className="-ml-2 mr-4 h-full w-[240px] shrink-0 rounded-2xl bg-ds-bg-neutral-default-default">
          <div className="flex flex-col gap-4">
            {KNOWLEDGE_SOURCE_GROUPS.map((group) => (
              <div key={group.id} className="flex flex-col gap-1">
                <div className="px-3 py-2 text-body-sm font-bold text-ds-text-neutral-default-default">
                  {group.label}
                </div>
                <div className="flex flex-col gap-1">
                  {knowledgeSourcesInGroup(group.id).map((source) => {
                    const isActive = selectedId === source.id;
                    const tone =
                      source.id === "ima"
                        ? imaDotTone()
                        : source.comingSoon
                          ? "muted"
                          : null;
                    return (
                      <button
                        key={source.id}
                        type="button"
                        onClick={() => selectSource(source)}
                        className={cn(
                          "flex w-full items-center justify-between rounded-xl px-3 py-2 transition-colors duration-200",
                          isActive
                            ? "bg-ds-bg-neutral-subtle-default hover:bg-ds-bg-neutral-subtle-default"
                            : "bg-transparent hover:bg-ds-bg-neutral-subtle-default/70",
                        )}
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <img
                            src={getKnowledgeLogo(source.id)}
                            alt={source.name}
                            className="h-5 w-5 shrink-0 object-contain"
                          />
                          <span
                            className={cn(
                              "truncate text-body-sm font-medium",
                              isActive
                                ? "text-ds-text-neutral-default-default"
                                : "text-ds-text-neutral-muted-default",
                            )}
                          >
                            {source.name}
                          </span>
                        </div>
                        <StatusDot tone={tone} />
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <ConfigModelCard status={selected.id === "ima" ? ring : "idle"}>
            <div className="mx-6 mb-4 flex flex-col items-start justify-between border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default pb-4 pt-2">
              <div className="inline-flex items-center justify-between gap-2 self-stretch">
                <div className="inline-flex items-center gap-2">
                  <img
                    src={getKnowledgeLogo(selected.id)}
                    alt={selected.name}
                    className="h-6 w-6 shrink-0 object-contain"
                  />
                  <div className="text-body-base my-2 font-bold text-ds-text-neutral-default-default">
                    {selected.name}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {selected.comingSoon ? (
                    <Button
                      variant="secondary"
                      size="xs"
                      disabled
                      className="!rounded-full font-bold"
                    >
                      即将推出
                    </Button>
                  ) : imaConfigured ? (
                    <Button
                      variant="primary"
                      size="xs"
                      disabled
                      className="!rounded-full !border-ds-text-success-default-default !bg-ds-text-success-default-default font-bold"
                    >
                      已配置
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
                  <StatusDot
                    tone={
                      selected.comingSoon
                        ? "muted"
                        : imaDotTone()
                    }
                  />
                </div>
              </div>
              <div className="text-body-sm text-ds-text-neutral-muted-default">
                {selected.description}
              </div>
            </div>

            {selected.comingSoon ? (
              <div className="flex w-full flex-col gap-3 px-6 pb-6">
                <p className="text-body-sm text-ds-text-neutral-muted-default">
                  此知识库源尚未接入。当前可配置腾讯 ima；后续会在此填写连接信息。
                </p>
                {selected.docsUrl ? (
                  <a
                    href={selected.docsUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-body-sm text-ds-text-brand-default-default hover:underline"
                  >
                    了解产品
                    <ExternalLink className="size-3.5" />
                  </a>
                ) : null}
              </div>
            ) : (
              <>
                <div className="flex w-full flex-col items-center gap-4 px-6">
                  <SettingsField
                    title="Client ID"
                    type="text"
                    value={clientId}
                    onChange={(e) => {
                      setClientId(e.target.value);
                      setFieldError("");
                    }}
                    autoComplete="off"
                    placeholder="ima-openapi-clientid"
                  />
                  <SettingsField
                    title="API Key"
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => {
                      setApiKey(e.target.value);
                      setFieldError("");
                    }}
                    autoComplete="off"
                    placeholder="ima-openapi-apikey"
                    backIcon={
                      showKey ? <Eye className="h-5 w-5" /> : <EyeOff className="h-5 w-5" />
                    }
                    onBackIconClick={() => setShowKey((v) => !v)}
                  />
                  {selected.docsUrl ? (
                    <a
                      href={selected.docsUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="self-start inline-flex items-center gap-1 text-body-sm text-ds-text-brand-default-default hover:underline"
                    >
                      申请凭证
                      <ExternalLink className="size-3.5" />
                    </a>
                  ) : null}
                </div>
                <div className="flex justify-end gap-2 px-6 py-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="font-medium"
                    disabled={busy}
                    onClick={() => void testConnection()}
                  >
                    测试连接
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    className="font-bold"
                    disabled={busy}
                    onClick={() => void save()}
                  >
                    {saving ? "保存中…" : "保存"}
                  </Button>
                </div>
                {(fieldError || status) && (
                  <p
                    role="status"
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
              </>
            )}
          </ConfigModelCard>
        </div>
      </div>
    </div>
  );
}
