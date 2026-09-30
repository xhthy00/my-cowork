import { apiFetch as fetch } from "@/api/backend";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ModelConnection, ModelProfile, ModelsState } from "@/window";
import {
  capabilityFor,
  runtimeCapability,
  type ModelCatalog,
} from "../../../../electron/model_capabilities";
import {
  ConnectionEditor,
  ModelEditor,
  Feedback,
  type Notice,
} from "./ModelConfigEditor";
import "./model-config.css";

type Editor =
  | { kind: "connection"; connection?: ModelConnection }
  | { kind: "model"; connection: ModelConnection; model?: ModelProfile };

export default function ModelsPanel() {
  const [models, setModels] = useState<ModelsState>({
    profiles: [],
    activeId: null,
  });
  const [catalog, setCatalog] = useState<ModelCatalog>({
    models: [],
    updatedAt: "",
  });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [editor, setEditor] = useState<Editor>();
  const [busy, setBusy] = useState(false);
  const [ratio, setRatio] = useState("80");
  const [ratioNotice, setRatioNotice] = useState<Notice>();
  const [rowNotice, setRowNotice] = useState<{ id: string; notice: Notice }>();
  const [keyStates, setKeyStates] = useState<Record<string, boolean | null>>(
    {},
  );
  const ratioDirty =
    Number(ratio) !==
    Number(((models.compactionRatio ?? 0.8) * 100).toFixed(6));

  useEffect(() => {
    let cancelled = false;
    void window.api
      .getModels()
      .then((s) => {
        if (cancelled) return;
        setModels(s);
        setRatio(String(Number(((s.compactionRatio ?? 0.8) * 100).toFixed(6))));
      })
      .catch((e) => {
        if (!cancelled) setLoadError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    const readCatalog = () =>
      void window.api
        .getModelCatalog?.()
        .then((c) => {
          if (!cancelled) setCatalog(c);
        })
        .catch((e) => {
          // Offline fallback; maintenance is not part of this screen.
        });
    readCatalog();
    const unsubscribe = window.api.onModelCatalogChanged?.(readCatalog);
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Account references can exist before keys are saved. Retain only presence.
    void Promise.all(
      (models.connections ?? []).map(async (c) => {
        try {
          return [
            c.id,
            c.keyAccount
              ? Boolean(await window.api.getKey(c.keyAccount))
              : false,
          ] as const;
        } catch {
          return [c.id, null] as const;
        }
      }),
    ).then((entries) => {
      if (!cancelled) setKeyStates(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [models.connections]);

  function publish(next: ModelsState) {
    setModels(next);
    window.dispatchEvent(new Event("my-cowork:models-changed"));
  }
  async function setDefault(p: ModelProfile) {
    setBusy(true);
    setRowNotice(undefined);
    try {
      publish(await window.api.setActiveModel(p.id));
      setRowNotice({
        id: p.id,
        notice: {
          kind: "success",
          text: "已设为新会话默认模型。",
        },
      });
    } catch (e) {
      setRowNotice({ id: p.id, notice: { kind: "error", text: String(e) } });
    } finally {
      setBusy(false);
    }
  }
  async function saveRatio() {
    setBusy(true);
    setRatioNotice(undefined);
    try {
      const value = Number(ratio);
      if (!Number.isFinite(value) || value < 10 || value > 95)
        throw new Error("请输入 10 到 95 之间的百分比");
      publish(await window.api.setCompactionRatio(value / 100));
      setRatioNotice({ kind: "success", text: "自动压缩阈值已保存。" });
    } catch (e) {
      setRatioNotice({
        kind: "error",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="model-config">
      <header className="model-page-heading">
        <h2>模型配置/上下文</h2>
      </header>
      <section className="model-settings-section" aria-label="连接与模型">
        <div className="model-section-heading">
          <div>
            <h3>连接与模型</h3>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={loading || busy || !!loadError}
            onClick={() => setEditor({ kind: "connection" })}
          >
            添加连接
          </Button>
        </div>
        {loading && (
          <p className="model-muted" role="status">
            正在读取配置…
          </p>
        )}
        {loadError && (
          <Feedback
            notice={{ kind: "error", text: `读取配置失败：${loadError}` }}
          />
        )}
        {!loading && !loadError && !models.connections?.length && (
          <div className="model-empty">
            <p>尚未添加连接</p>
          </div>
        )}
        <div className="model-connections">
          {models.connections?.map((c) => {
            const profiles = models.profiles.filter(
              (p) => p.connectionId === c.id,
            );
            return (
              <section
                key={c.id}
                className="model-connection-card"
                aria-label={`连接 ${c.name}`}
              >
                <header className="model-connection-heading">
                  <div className="model-connection-identity">
                    <div>
                      <h3>{c.name}</h3>
                      <p>
                        {c.baseUrl} ·{" "}
                        {keyStates[c.id] === true
                          ? "密钥已配置"
                          : keyStates[c.id] === false
                            ? c.category === "local"
                              ? "本地连接 · 无密钥"
                              : "未配置密钥"
                            : "密钥状态待确认"}
                      </p>
                    </div>
                  </div>
                  <div className="model-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      aria-label={`编辑连接 ${c.name}`}
                      onClick={() =>
                        setEditor({ kind: "connection", connection: c })
                      }
                    >
                      编辑连接
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      aria-label={`添加模型到 ${c.name}`}
                      onClick={() =>
                        setEditor({ kind: "model", connection: c })
                      }
                    >
                      添加模型
                    </Button>
                  </div>
                </header>
                {profiles.length === 0 && (
                  <p className="model-empty-row">
                    连接已保存，添加一个模型开始使用。
                  </p>
                )}
                {profiles.map((p) => {
                  return (
                    <div key={p.id} className="model-summary-row">
                      <div className="model-summary-main">
                        <div className="model-name-line">
                          <strong>{p.name || p.model}</strong>
                          {p.id === models.activeId && (
                            <span className="model-default-badge">
                              新会话默认
                            </span>
                          )}
                        </div>
                        {p.model !== p.name && <code>{p.model}</code>}
                      </div>
                      <div className="model-actions">
                        {p.id !== models.activeId && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            aria-label={`设为默认 ${p.name}`}
                            onClick={() => void setDefault(p)}
                          >
                            设为默认
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          aria-label={`编辑 ${p.name}`}
                          onClick={() =>
                            setEditor({
                              kind: "model",
                              connection: c,
                              model: p,
                            })
                          }
                        >
                          编辑
                        </Button>
                      </div>
                      {rowNotice?.id === p.id && (
                        <div className="model-row-feedback">
                          <Feedback notice={rowNotice.notice} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </section>
            );
          })}
        </div>
      </section>
      <section className="model-settings-section" aria-label="上下文">
        <div className="model-section-heading">
          <h3>上下文</h3>
        </div>
        {models.profiles.length > 0 && (
          <table className="model-context-table" aria-label="模型上下文窗口">
            <colgroup>
              <col />
              <col className="model-context-capacity-col" />
              <col className="model-context-source-col" />
              <col className="model-context-action-col" />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">模型</th>
                <th scope="col">窗口 · tokens</th>
                <th scope="col">设置方式</th>
                <th scope="col">
                  <span className="sr-only">操作</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {models.profiles.map((p) => (
                <ContextWindowRow
                  key={p.id}
                  model={p}
                  catalog={catalog}
                  onPublish={publish}
                />
              ))}
            </tbody>
          </table>
        )}
        <div className="model-compression-row">
          <div className="model-compression-label">
            <label htmlFor="model-compaction-ratio">自动压缩</label>
            <span className="model-caption">所有模型</span>
          </div>
          <div className="model-compression-controls">
            <div className="model-percent-control">
              <input
                id="model-compaction-ratio"
                aria-label="自动压缩阈值"
                className="model-setting-input"
                type="number"
                min={10}
                max={95}
                step="any"
                value={ratio}
                disabled={loading || busy || !!loadError}
                onChange={(e) => {
                  setRatio(e.target.value);
                  setRatioNotice(undefined);
                }}
              />
              <span aria-hidden="true">%</span>
            </div>
            <Button
              size="sm"
              variant="outline"
              aria-label="保存阈值"
              disabled={loading || busy || !!loadError || !ratioDirty}
              onClick={() => void saveRatio()}
            >
              保存
            </Button>
          </div>
          <Feedback notice={ratioNotice} />
        </div>
      </section>
      {editor?.kind === "connection" && (
        <ConnectionEditor
          connection={editor.connection}
          modelCount={
            models.profiles.filter(
              (p) => p.connectionId === editor.connection?.id,
            ).length
          }
          onPublish={publish}
          onClose={() => setEditor(undefined)}
        />
      )}
      {editor?.kind === "model" && (
        <ModelEditor
          connection={editor.connection}
          model={editor.model}
          catalog={catalog}
          onPublish={publish}
          onClose={() => setEditor(undefined)}
        />
      )}
    </div>
  );
}

function ContextWindowRow({
  model,
  catalog,
  onPublish,
}: {
  model: ModelProfile;
  catalog: ModelCatalog;
  onPublish: (state: ModelsState) => void;
}) {
  const cap = capabilityFor(model, catalog);
  const automaticWindow = cap?.context ?? 200000;
  const currentWindow = model.contextWindow ?? automaticWindow;
  const [editing, setEditing] = useState(false);
  const [mode, setMode] = useState("auto");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>();
  const adjustRef = useRef<HTMLButtonElement>(null);
  const dirty =
    mode === "auto"
      ? model.contextWindow !== undefined
      : value !== model.contextWindow?.toString();
  function open() {
    setMode(model.contextWindow === undefined ? "auto" : "custom");
    setValue(currentWindow.toString());
    setNotice(undefined);
    setEditing(true);
  }
  function close() {
    setEditing(false);
    setNotice(undefined);
    requestAnimationFrame(() => adjustRef.current?.focus());
  }
  async function save() {
    if (!dirty || busy) return;
    setBusy(true);
    setNotice(undefined);
    try {
      if (mode === "custom" && !value.trim())
        throw new Error("请输入上下文窗口");
      const contextWindow = mode === "custom" ? Number(value) : undefined;
      runtimeCapability({ ...model, contextWindow, reasoning: {} }, catalog);
      onPublish(
        await window.api.upsertModel({
          ...model,
          contextWindow,
          activate: false,
        }),
      );
      close();
    } catch (e) {
      setNotice({
        kind: "error",
        text: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <tr className="model-window-row">
        <th scope="row">{model.name || model.model}</th>
        <td className="model-window-value">{currentWindow.toLocaleString()}</td>
        <td
          className="model-window-source"
          title={
            !cap && model.contextWindow === undefined
              ? "未识别容量，暂用 200,000 tokens"
              : undefined
          }
        >
          {model.contextWindow !== undefined ? "自定义" : cap ? "自动" : "暂用"}
        </td>
        <td className="model-window-action">
          <Button
            ref={adjustRef}
            size="sm"
            variant="ghost"
            aria-label={`调整上下文 ${model.name}`}
            aria-expanded={editing}
            aria-controls={`context-editor-${model.id}`}
            disabled={editing}
            onClick={open}
          >
            调整
          </Button>
        </td>
      </tr>
      {editing && (
        <tr className="model-window-edit-row">
          <td colSpan={4}>
            <form
              id={`context-editor-${model.id}`}
              aria-label={`调整上下文 ${model.name}`}
              className="model-window-editor"
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape" && !busy) {
                  e.preventDefault();
                  close();
                }
              }}
            >
              <div className="model-window-fields">
                <label>
                  设置方式
                  <select
                    className="model-setting-input"
                    aria-label={`窗口设置方式 ${model.name}`}
                    autoFocus
                    disabled={busy}
                    value={mode}
                    onChange={(e) => {
                      setMode(e.target.value);
                      setNotice(undefined);
                    }}
                  >
                    <option value="auto">自动</option>
                    <option value="custom">自定义</option>
                  </select>
                </label>
                <label>
                  窗口（tokens）
                  <input
                    className="model-setting-input"
                    aria-label={`上下文窗口 ${model.name}`}
                    type="number"
                    min={4096}
                    max={10000000}
                    value={mode === "auto" ? automaticWindow : value}
                    disabled={busy || mode === "auto"}
                    onChange={(e) => {
                      setValue(e.target.value);
                      setNotice(undefined);
                    }}
                  />
                </label>
              </div>
              {!cap && mode === "auto" && (
                <p className="model-caption">未识别容量，暂用 200,000 tokens</p>
              )}
              <Feedback notice={notice} />
              <div className="model-window-editor-actions">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  aria-label="取消调整"
                  onClick={close}
                >
                  取消
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={busy || !dirty}
                  aria-label="保存窗口"
                >
                  保存
                </Button>
              </div>
            </form>
          </td>
        </tr>
      )}
    </>
  );
}
