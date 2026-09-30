import { useEffect, useRef, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { CheckCircle2, AlertCircle, X, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SettingsField } from "./SettingsField";
import {
  BYOK_PRESETS,
  LOCAL_PRESETS,
  findPreset,
  modelListUrl,
} from "@/lib/modelPresets";
import {
  runtimeCapability,
  type ModelCatalog,
} from "../../../../electron/model_capabilities";
import type {
  ModelConnection,
  ModelProfile,
  ModelsState,
  ReasoningSelection,
} from "@/window";

export type Notice = { kind: "success" | "error"; text: string };
export function Feedback({ notice }: { notice?: Notice }) {
  if (!notice) return null;
  return (
    <div
      className={`model-feedback ${notice.kind}`}
      role={notice.kind === "error" ? "alert" : "status"}
    >
      {notice.kind === "error" ? (
        <AlertCircle size={16} />
      ) : (
        <CheckCircle2 size={16} />
      )}
      <span>{notice.text}</span>
    </div>
  );
}

function EditorShell({
  title,
  description,
  dirty,
  busy,
  onClose,
  children,
  footer,
  notice,
  onDelete,
  deleteDescription,
}: {
  title: string;
  description: string;
  dirty: boolean;
  busy: boolean;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  notice?: Notice;
  onDelete?: () => void;
  deleteDescription?: string;
}) {
  const [confirmation, setConfirmation] = useState<"discard" | "delete">();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(
    document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  );
  useEffect(() => {
    if (confirmation) cancelRef.current?.focus();
  }, [confirmation]);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  function close() {
    if (busy) return;
    if (dirty) setConfirmation("discard");
    else onClose();
  }
  function cancelConfirmation() {
    setConfirmation(undefined);
    closeRef.current?.focus();
  }
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="model-editor-overlay" />
        <Dialog.Content
          className="model-editor"
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            const target = returnFocus.current?.isConnected
              ? returnFocus.current
              : document.querySelector<HTMLElement>(
                  ".model-section-heading button",
                );
            target?.focus();
          }}
          onEscapeKeyDown={(e) => {
            e.preventDefault();
            if (confirmation) cancelConfirmation();
            else close();
          }}
          onPointerDownOutside={(e) => {
            e.preventDefault();
            if (!confirmation) close();
          }}
        >
          <header className="model-editor-header">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description>{description}</Dialog.Description>
            </div>
            <Button
              ref={closeRef}
              variant="ghost"
              size="icon"
              aria-label="关闭编辑面板"
              disabled={busy}
              onClick={close}
            >
              <X size={18} />
            </Button>
          </header>
          <div className="model-editor-scroll">
            <fieldset
              disabled={busy || !!confirmation}
              className="model-editor-fields"
            >
              {children}
            </fieldset>
          </div>
          <footer className="model-editor-footer">
            {confirmation ? (
              <div className="model-editor-confirm" role="alert">
                <strong>
                  {confirmation === "discard"
                    ? "有尚未保存的修改"
                    : "确认删除？"}
                </strong>
                <p>
                  {confirmation === "discard"
                    ? "放弃后，这次修改将不会保存。"
                    : deleteDescription}
                </p>
                <div className="model-actions">
                  <Button
                    ref={cancelRef}
                    variant="outline"
                    disabled={busy}
                    onClick={cancelConfirmation}
                  >
                    {confirmation === "discard" ? "继续编辑" : "取消"}
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={busy}
                    onClick={() => {
                      if (confirmation === "discard") onClose();
                      else {
                        setConfirmation(undefined);
                        onDelete?.();
                      }
                    }}
                  >
                    {confirmation === "discard" ? "放弃修改" : "确认删除"}
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <Feedback notice={notice} />
                <div className="model-editor-footer-actions">
                  {onDelete && (
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => setConfirmation("delete")}
                    >
                      删除{title.includes("连接") ? "连接" : "模型"}
                    </Button>
                  )}
                  <div className="model-actions">
                    {dirty && <span className="model-caption">未保存</span>}
                    {footer}
                  </div>
                </div>
              </>
            )}
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

type EditorProps = { onPublish: (s: ModelsState) => void; onClose: () => void };

export function ConnectionEditor({
  connection,
  modelCount,
  onPublish,
  onClose,
}: EditorProps & { connection?: ModelConnection; modelCount: number }) {
  const [presetId, setPresetId] = useState(
    connection?.presetId ??
      (connection?.provider === "anthropic" || !connection
        ? "anthropic"
        : "openai-compatible-model"),
  );
  const preset = findPreset(presetId) ?? BYOK_PRESETS[0];
  const [name, setName] = useState(connection?.name ?? preset.name);
  const [baseUrl, setBaseUrl] = useState(
    connection?.baseUrl ?? preset.defaultHost,
  );
  const [apiKey, setApiKey] = useState("");
  const draft = JSON.stringify({ presetId, name, baseUrl, apiKey });
  const baseline = useRef(draft);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>();
  async function save() {
    setBusy(true);
    setNotice(undefined);
    try {
      if (!name.trim()) throw new Error("请填写连接名称");
      try {
        const url = new URL(baseUrl.trim());
        if (!["http:", "https:"].includes(url.protocol)) throw new Error();
      } catch {
        throw new Error("请填写有效的 http 或 https 接口地址");
      }
      onPublish(
        await window.api.upsertConnection({
          id: connection?.id ?? "",
          name: name.trim(),
          provider: connection?.provider ?? preset.provider,
          baseUrl: baseUrl.trim(),
          presetId,
          category: connection?.category ?? preset.category,
          apiKey: apiKey.trim() || undefined,
        }),
      );
      onClose();
    } catch (e) {
      setNotice({
        kind: "error",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!connection) return;
    setBusy(true);
    setNotice(undefined);
    try {
      onPublish(await window.api.removeConnection(connection.id));
      onClose();
    } catch (e) {
      setNotice({ kind: "error", text: String(e) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <EditorShell
      title={connection ? "编辑连接" : "添加连接"}
      description={
        connection
          ? `${connection.name} · 此处修改会应用到该连接下的 ${modelCount} 个模型。`
          : "先保存服务地址与密钥，再为连接添加模型。"
      }
      dirty={draft !== baseline.current}
      busy={busy}
      onClose={onClose}
      notice={notice}
      onDelete={connection ? () => void remove() : undefined}
      deleteDescription={`将删除“${connection?.name}”及其全部 ${modelCount} 个模型。`}
      footer={
        <Button disabled={busy} onClick={() => void save()}>
          {busy ? "保存中…" : "保存连接"}
        </Button>
      }
    >
      {!connection && (
        <label className="model-form-label">
          服务类型
          <select
            aria-label="服务类型"
            value={presetId}
            onChange={(e) => {
              const p = findPreset(e.target.value);
              if (p) {
                setPresetId(p.id);
                setName(p.name);
                setBaseUrl(p.defaultHost);
                setApiKey("");
              }
            }}
          >
            <optgroup label="云端服务">
              {BYOK_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </optgroup>
            <optgroup label="本地服务">
              {LOCAL_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
      )}
      {connection && (
        <p className="model-form-note">
          接口类型：
          {connection.provider === "anthropic" ? "Anthropic" : "OpenAI 兼容"}
        </p>
      )}
      <SettingsField
        title="连接名称"
        aria-label="连接名称"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="例如：公司服务、个人账号"
      />
      <SettingsField
        title="接口地址"
        aria-label="Base URL"
        value={baseUrl}
        onChange={(e) => setBaseUrl(e.target.value)}
        placeholder={preset.defaultHost}
      />
      <SettingsField
        title={preset.requiresApiKey ? "API 密钥" : "API 密钥（可选）"}
        aria-label="API 密钥"
        type="password"
        autoComplete="new-password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={
          connection ? "留空保留原有密钥，输入新值可替换" : "输入 API 密钥"
        }
      />
    </EditorShell>
  );
}

export function ModelEditor({
  connection,
  model,
  catalog,
  onPublish,
  onClose,
}: EditorProps & {
  connection: ModelConnection;
  model?: ModelProfile;
  catalog: ModelCatalog;
}) {
  const preset =
    findPreset(connection.presetId) ??
    findPreset(
      connection.provider === "anthropic"
        ? "anthropic"
        : "openai-compatible-model",
    )!;
  const [savedId, setSavedId] = useState(model?.id);
  const [modelId, setModelId] = useState(model?.model ?? preset.defaultModel);
  const [name, setName] = useState(model?.name ?? "");
  const [reasoning, setReasoning] = useState<ReasoningSelection>(
    model?.reasoning ?? {},
  );
  const [contextWindow] = useState(
    model?.contextWindow ? String(model.contextWindow) : "",
  );
  const [capabilityId, setCapabilityId] = useState(model?.capabilityId ?? "");
  const [adapter, setAdapter] = useState(model?.reasoningAdapter ?? "");
  const [remoteModels, setRemoteModels] = useState<string[]>([]);
  const [listNotice, setListNotice] = useState<Notice>();
  const [notice, setNotice] = useState<Notice>();
  const [busy, setBusy] = useState(false);
  const draft = JSON.stringify({
    modelId,
    name,
    reasoning,
    contextWindow,
    capabilityId,
    adapter,
  });
  const [baseline, setBaseline] = useState(draft);
  const dirty = draft !== baseline;
  const profile: ModelProfile = {
    id: savedId ?? "",
    connectionId: connection.id,
    provider: connection.provider,
    baseUrl: connection.baseUrl,
    presetId: connection.presetId,
    category: connection.category,
    model: modelId.trim(),
    name: name.trim() || modelId.trim(),
    reasoning,
    contextWindow: contextWindow ? Number(contextWindow) : undefined,
    capabilityId: capabilityId || undefined,
    reasoningAdapter: adapter || undefined,
  };
  // Changing a draft invalidates feedback about the previous configuration.
  useEffect(() => {
    setNotice(undefined);
  }, [draft]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setNotice(undefined);
    try {
      await action();
    } catch (e) {
      setNotice({
        kind: "error",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!modelId.trim()) throw new Error("请填写模型 ID");
    runtimeCapability(profile, catalog);
    const next = await window.api.upsertModel({
      ...profile,
      id: savedId,
      activate: false,
    });
    onPublish(next);
    const saved =
      next.profiles.find((p) => p.id === savedId) ??
      next.profiles.find(
        (p) => p.connectionId === connection.id && p.model === profile.model,
      );
    if (!saved) throw new Error("保存结果中未找到模型，请重新打开配置检查");
    setSavedId(saved.id);
    setBaseline(draft);
    setNotice({
      kind: "success",
      text: "模型已保存。",
    });
  }
  async function probe() {
    if (!savedId || dirty) return;
    const result = await window.api.validateModel?.({
      profileId: savedId,
      provider: connection.provider,
      model: profile.model,
      baseUrl: connection.baseUrl,
    });
    if (!result?.ok) throw new Error(result?.error || "连接测试失败");
    setNotice({
      kind: "success",
      text: `连接成功${result.latency_ms != null ? ` · ${result.latency_ms} ms` : ""}。`,
    });
  }
  async function listModels() {
    setListNotice(undefined);
    const url = modelListUrl(connection.baseUrl ?? "", preset);
    if (!url || !preset.parseModels)
      throw new Error("此服务暂不支持获取列表，请手动填写模型 ID");
    const key = connection.keyAccount
      ? await window.api.getKey(connection.keyAccount)
      : "";
    const response = await fetch(url, {
      headers: key ? { Authorization: `Bearer ${key}` } : {},
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error(`获取模型列表失败（${response.status}）`);
    const ids = preset.parseModels(await response.json());
    setRemoteModels(ids);
    setListNotice({
      kind: "success",
      text: ids.length
        ? `已获取 ${ids.length} 个模型，可从下方选择或手动输入。`
        : "服务返回空列表，请手动填写模型 ID。",
    });
  }
  function changeModel(value: string) {
    setModelId(value);
    setReasoning({});
    setCapabilityId("");
  }
  return (
    <EditorShell
      title={savedId ? "编辑模型" : "添加模型"}
      description={connection.name}
      dirty={dirty}
      busy={busy}
      onClose={onClose}
      notice={notice}
      onDelete={
        savedId
          ? () =>
              void run(async () => {
                onPublish(await window.api.removeModel(savedId));
                onClose();
              })
          : undefined
      }
      deleteDescription={`将删除模型“${name || modelId}”，保留连接和其他模型。`}
      footer={
        <>
          <Button
            variant="outline"
            disabled={busy || dirty || !savedId}
            title={
              dirty || !savedId
                ? "请先保存模型"
                : "调用当前模型测试连接，可能消耗 tokens"
            }
            onClick={() => void run(probe)}
          >
            测试连接
          </Button>
          <Button
            disabled={busy || (!!savedId && !dirty)}
            onClick={() => void run(save)}
          >
            {busy ? "处理中…" : "保存模型"}
          </Button>
        </>
      }
    >
      <section className="model-editor-section">
        <SettingsField
          title="模型 ID"
          aria-label="模型 ID"
          value={modelId}
          onChange={(e) => changeModel(e.target.value)}
          placeholder="服务实际接受的模型名称"
        />
        {preset.parseModels && (
          <div className="model-list-picker">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void run(listModels)}
            >
              获取模型列表
            </Button>
          </div>
        )}
        <Feedback notice={listNotice} />
        {remoteModels.length > 0 && (
          <label className="model-form-label">
            服务中的模型
            <select
              aria-label="选择服务模型"
              value={remoteModels.includes(modelId) ? modelId : ""}
              onChange={(e) => {
                if (e.target.value) changeModel(e.target.value);
              }}
            >
              <option value="">选择模型…</option>
              {remoteModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        )}
        <SettingsField
          title="显示名称（可选）"
          aria-label="模型显示名称"
          value={name}
          placeholder={modelId || "便于识别的名称"}
          onChange={(e) => setName(e.target.value)}
        />
      </section>
      <details className="model-advanced">
        <summary>
          兼容性设置
          <ChevronDown size={15} />
        </summary>
        <div className="model-advanced-fields">
          <p className="model-form-note">
            适用于中转别名或私有部署。关联基础模型不会改变实际请求 ID。
          </p>
          <SettingsField
            title="关联基础模型"
            aria-label="关联能力"
            value={capabilityId}
            list="capability-models"
            placeholder="自动识别"
            onChange={(e) => {
              setCapabilityId(e.target.value);
              setReasoning({});
            }}
          />
          <datalist id="capability-models">
            {catalog.models
              .filter((m) =>
                (capabilityId ? m.id : m.model)
                  .toLowerCase()
                  .includes((capabilityId || modelId).toLowerCase()),
              )
              .slice(0, 80)
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
          </datalist>
          <label className="model-form-label">
            思考参数协议
            <select
              aria-label="思考参数协议"
              value={adapter}
              onChange={(e) => setAdapter(e.target.value)}
            >
              <option value="">根据连接自动选择</option>
              {[
                "openai",
                "openai-responses",
                "anthropic",
                "deepseek",
                "moonshot",
                "qwen",
                "openrouter",
                "thinking",
                "google",
                "minimax",
              ].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>
    </EditorShell>
  );
}
