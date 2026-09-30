import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Boxes, RefreshCw, Upload, MoreHorizontal, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import type { IndustryStatus } from "@/window";
import { usePageTabStore } from "@/store/pageTab";
import { leaveIndustryPage, useIndustryNavigation } from "@/store/industryNavigation";
import { appAIRequest, startAppTask, useAppTasks, isAppTaskRunning, type AppTask } from "@/api/industryAI";
import IndustryAIPanel, { openAppFile } from "./IndustryAIPanel";

type InstalledApp = Awaited<ReturnType<typeof window.api.industryList>>["apps"][number];
type Inspection = Awaited<ReturnType<typeof window.api.industryInspect>>;

const CHANNEL = "mycowork-app/v1";

export default function IndustryWorkbench() {
  const [apps, setApps] = useState<InstalledApp[]>([]);
  const activeId = useIndustryNavigation(state => state.activeId);
  const setActiveId = (id: string | null) => {
    if (!leaveIndustryPage()) return false;
    useIndustryNavigation.setState({ activeId: id });
    return true;
  };
  const [aiOpen, setAiOpen] = useState(false);
  const [aiSelected, setAiSelected] = useState<string | null>(null);
  const aiRecords = useAppTasks(state => state.records);
  const [pending, setPending] = useState<{ filePath: string; details: Inspection } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lifecycle, setLifecycle] = useState<IndustryStatus>({ busy: false, phase: "idle" });
  const [dismissedNotice, setDismissedNotice] = useState("");
  const [operation, setOperation] = useState<Awaited<ReturnType<typeof window.api.industryList>>["operation"]>();
  const [confirmation, setConfirmation] = useState<{ entry: InstalledApp; action: "disable" | "enable" | "rollback" | "remove" | "retry" } | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLButtonElement | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [frameRevision, setFrameRevision] = useState(0);
  const [bridgeToken] = useState(() => {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  });
  const frameRef = useRef<HTMLIFrameElement>(null);
  const initialRefresh = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const result = await window.api.industryList();
      setApps(result.apps);
      if (result.lifecycle) setLifecycle(result.lifecycle);
      setOperation(result.operation);
      if (initialRefresh.current) {
        initialRefresh.current = false;
        const status = result.lifecycle;
        if (status && !status.busy && !status.detail && !result.operation?.error && !result.operation?.retained && ["committed", "cancelled"].includes(status.phase)) {
          setDismissedNotice(`${status.phase}:${status.generation}:${status.message}`);
        }
      }
      const source = useIndustryNavigation.getState().activeId;
      setError(source && !result.apps.some(entry => entry.id === source) ? "来源应用已移除。AI 记录仍保留在工作区，可从这里打开其他应用。" : "");
      if (source && !result.apps.some(entry => entry.id === source)) useIndustryNavigation.setState({ activeId: null, dirty: false });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  useEffect(() => {
    void refresh();
    return window.api.onBackendReady?.(() => {
      void refresh();
    });
  }, [refresh]);

  useEffect(() => {
    return window.api.onIndustryStatus?.((status) => {
      setLifecycle(status);
      if (status.busy) setDismissedNotice("");
      if (!status.busy) void refresh();
    });
  }, [refresh]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (pending || confirmation) {
      if (dialog && !dialog.open) dialog.showModal();
    } else if (dialog?.open) {
      dialog.close();
    }
  }, [pending, confirmation]);

  const working = busy || lifecycle.busy;
  const noticeKey = `${lifecycle.phase}:${lifecycle.generation}:${lifecycle.message}`;
  useEffect(() => {
    if (lifecycle.busy || lifecycle.detail || operation?.retained || !["committed", "cancelled"].includes(lifecycle.phase)) return;
    const timer = window.setTimeout(() => setDismissedNotice(noticeKey), 5000);
    return () => window.clearTimeout(timer);
  }, [lifecycle.busy, lifecycle.detail, lifecycle.phase, noticeKey, operation?.retained]);
  const switching = lifecycle.busy && !["staged", "draining"].includes(lifecycle.phase);
  const labels: Record<string, string> = { ready: "可用", disabled: "已停用", pending_activation: "待启用", pending_restart: "待启用", recovery_required: "需要恢复", load_failed: "启用失败" };
  const progress = lifecycle.phase === "draining"
    ? `等待 ${lifecycle.active || 0} 项工作结束`
    : ({ staged: "正在准备", snapshot_ready: "正在保存数据", starting: "正在启用应用", restarting: "正在启动", restoring: "正在恢复原版本和数据" } as Record<string, string>)[lifecycle.phase];
  const active = apps.find((entry) => entry.id === activeId);
  const visibleAppId = active?.id;
  // Route declarations are return bookmarks, not a reason to navigate a live iframe.
  const initialRoute = useMemo(() => active?.id ? useIndustryNavigation.getState().routes[active.id] || "/" : "/", [active?.id, active?.generation, frameRevision]);
  const frameSrc = active?.status === "ready" && !switching
    ? (active.dev_url ? active.dev_url + "/" : "mycowork-app://" + active.id + "/" + active.generation + "/index.html") + "?bridge=" + bridgeToken + "&hostOrigin=" + encodeURIComponent(window.location.origin) + "#" + initialRoute
    : null;
  const appOrigin = active?.dev_url || "mycowork-app://" + visibleAppId;

  const sendAppearance = useCallback(() => {
    if (!frameSrc || !visibleAppId) return;
    const root = document.documentElement;
    const parsedScale = Number.parseFloat(getComputedStyle(root).getPropertyValue("--ui-font-scale"));
    frameRef.current?.contentWindow?.postMessage({
      channel: CHANNEL,
      appId: visibleAppId,
      bridgeToken,
      type: "host.appearance",
      theme: root.classList.contains("dark") || root.getAttribute("data-theme") === "dark" ? "dark" : "light",
      fontScale: Number.isFinite(parsedScale) && parsedScale >= 0.75 && parsedScale <= 1.5 ? parsedScale : 1,
    }, appOrigin);
  }, [visibleAppId, bridgeToken, frameSrc, appOrigin]);

  useEffect(() => {
    if (!activeId) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (useIndustryNavigation.getState().dirty) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [activeId]);

  useEffect(() => {
    if (!active || !frameSrc) return;
    frameRef.current?.contentWindow?.postMessage({ channel: CHANNEL, appId: active.id, bridgeToken,
      type: "host.ai.changed", tasks: Object.values(aiRecords).filter(task => task.origin.app_id === active.id).map(task => ({ task_id: task.task_id, status: task.status, updated_at: task.updated_at, files: task.files || [] })) }, appOrigin);
  }, [aiRecords, active, bridgeToken, frameSrc, appOrigin]);

  useEffect(() => {
    if (!frameSrc) return;
    const observer = new MutationObserver(sendAppearance);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "style"],
    });
    return () => observer.disconnect();
  }, [frameSrc, sendAppearance]);

  useEffect(() => {
    if (!frameSrc || !active) return;
    const onMessage = async (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.origin !== appOrigin) return;
      const message = event.data;
      if (!message || typeof message !== "object" || message.channel !== CHANNEL) return;
      if (message.bridgeToken !== bridgeToken) return;
      if (message.appId !== active.id || message.type !== "request" || typeof message.id !== "string") return;
      const reply = (payload: Record<string, unknown>) => {
        (event.source as Window).postMessage({
          channel: CHANNEL,
          appId: active.id,
          bridgeToken,
          id: message.id,
          type: "response",
          ...payload,
        }, event.origin);
      };
      try {
        if (!/^[a-zA-Z0-9_-]{1,100}$/.test(message.id)) throw new Error("invalid request id");
        let data: unknown;
        if (message.operation === "app.request") {
          if (typeof message.method !== "string" || typeof message.path !== "string") throw new Error("invalid request");
          data = await window.api.industryRequest(active.id, message.method, message.path, message.body, active.generation);
        } else if (message.operation === "ui.ready") {
          sendAppearance();
          data = { ok: true };
        } else {
          const capability = String(message.operation).split(".")[0];
          if (!active.manifest.capabilities?.host_api.includes(capability)) throw new Error("应用未声明此宿主能力");
          const taskId = typeof message.task_id === "string" ? encodeURIComponent(message.task_id) : "";
          switch (message.operation) {
            case "ai.startTask":
              if (!message.body || typeof message.body.prompt !== "string") throw new Error("请提供任务目标");
              data = await startAppTask(active.id, active.generation || "", { ...message.body,
                route: useIndustryNavigation.getState().routes[active.id] || "/" }, message.id);
              break;
            case "ai.listTasks": data = await appAIRequest(active.id, "/tasks"); break;
            case "ai.getTask": data = await appAIRequest(active.id, `/tasks/${taskId}`); break;
            case "ai.stopTask": data = await appAIRequest(active.id, `/tasks/${taskId}/cancel`, {}); break;
            case "ai.openTask": {
              const task = await appAIRequest<AppTask>(active.id, `/tasks/${taskId}`);
              setAiSelected(task.task_id); setAiOpen(true); data = { ok: true }; break;
            }
            case "files.pick": {
              const picked = await window.api.selectFile?.({ title: "选择本次 AI 可读取的文件（TXT、Markdown、CSV、JSON，2 MB 以内）" });
              const files = [];
              for (const file of picked?.files || []) files.push(await appAIRequest(active.id, "/files", { path: file.filePath, generation: active.generation }));
              data = { files }; break;
            }
            case "files.open":
              if (typeof message.file_id !== "string") throw new Error("文件引用无效");
              await openAppFile(active.id, message.file_id); data = { ok: true }; break;
            case "navigation.setRoute": {
              if (typeof message.route !== "string" || !message.route.startsWith("/") || message.route.startsWith("//") || message.route.includes("\\") || message.route.length > 2000) throw new Error("仅支持本应用内部路由");
              useIndustryNavigation.setState(state => ({ routes: { ...state.routes, [active.id]: message.route } }));
              data = { ok: true }; break;
            }
            case "ui.setDirty":
              if (typeof message.dirty !== "boolean") throw new Error("invalid dirty state");
              useIndustryNavigation.setState({ dirty: message.dirty }); data = { ok: true }; break;
            default: throw new Error("unsupported operation");
          }
        }
        reply({ ok: true, data });
      } catch (cause) {
        reply({ ok: false, error: cause instanceof Error ? cause.message : String(cause) });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [active, bridgeToken, frameSrc, appOrigin, sendAppearance]);

  async function choosePackage(appId?: string) {
    setError("");
    const picked = await window.api.selectFile?.({ title: "选择行业应用 ZIP" });
    const filePath = picked?.files?.[0]?.filePath;
    if (!filePath) return;
    setBusy(true);
    try {
      const details = await window.api.industryInspect(filePath);
      if (appId && details.manifest.id !== appId) throw new Error("所选 ZIP 属于另一个应用，请选择此应用的新版本");
      setPending({ filePath, details });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function installPackage() {
    if (!pending) return;
    const selected = pending;
    setPending(null);
    setBusy(true);
    try {
      await window.api.industryInstall(selected.filePath, selected.details.sha256);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  async function manageApp() {
    if (!confirmation) return;
    const { entry, action } = confirmation;
    setConfirmation(null);
    setBusy(true);
    try {
      await window.api.industryManage(entry.id, action);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  }

  function menu(entry: InstalledApp) {
    const needsRecovery = entry.status === "recovery_required" || (lifecycle.phase === "recovery_required" && lifecycle.appId === entry.id);
    return <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" disabled={working} aria-label={`管理 ${entry.manifest.name}`} onPointerDown={(event) => { returnFocus.current = event.currentTarget; }} onFocus={(event) => { returnFocus.current = event.currentTarget; }}>
          管理<MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {!entry.dev_revision && <DropdownMenuItem onSelect={() => void choosePackage(entry.id)}>从 ZIP 更新</DropdownMenuItem>}
        {!needsRecovery && <DropdownMenuItem onSelect={() => setConfirmation({ entry, action: entry.enabled && entry.status === "ready" ? "disable" : "enable" })}>
          {entry.enabled && entry.status === "ready" ? "停用" : "启用"}
        </DropdownMenuItem>}
        {entry.recovery && <DropdownMenuItem onSelect={() => setConfirmation({ entry, action: "rollback" })}>恢复上次更新</DropdownMenuItem>}
        {needsRecovery && <>
          <DropdownMenuItem onSelect={() => setConfirmation({ entry, action: "retry" })}>重试恢复</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setConfirmation({ entry, action: "disable" })}>停用并保留恢复数据</DropdownMenuItem>
        </>}
        <DropdownMenuItem onSelect={() => setConfirmation({ entry, action: "remove" })}>移除</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>;
  }

  const actionName = confirmation ? ({ disable: "停用", enable: "启用", rollback: "恢复上次更新", remove: "移除", retry: "重试恢复" })[confirmation.action] : "";
  const statusPanel = (lifecycle.busy || (lifecycle.message && dismissedNotice !== noticeKey)) && (
    <div className={active ? "shrink-0 border-b border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-4 py-2 text-sm" : "mb-4 rounded-lg border border-ds-border-neutral-subtle-default p-3 text-sm"}>
      <div className="flex items-center justify-between gap-3">
        <p role="status" aria-live="polite" className="m-0">{lifecycle.busy ? progress || "正在处理" : lifecycle.message}</p>
        {!lifecycle.busy && <button type="button" aria-label="关闭提示" className="shrink-0 rounded p-1 hover:bg-ds-bg-neutral-subtle-default" onClick={() => setDismissedNotice(noticeKey)}><X className="size-4" /></button>}
      </div>
      {lifecycle.phase === "pending_activation" && <Button className="mt-2" variant="outline" size="sm" onClick={() => usePageTabStore.getState().setHubTab("settings")}>打开模型设置</Button>}
      {lifecycle.phase === "draining" && <div className="mt-2 flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={() => usePageTabStore.getState().setWorkspaceView("workspace")}>查看任务</Button>
        <Button variant="outline" size="sm" onClick={() => void window.api.industryCancel()}>取消更新</Button>
        {!!lifecycle.tasks?.length && <details className="app-details"><summary>正在进行的工作</summary><ul>{lifecycle.tasks.map((task, index) => <li key={index}>{task}</li>)}</ul><p>可在原任务中继续回答或主动取消任务。</p></details>}
      </div>}
      {!lifecycle.busy && (operation?.error || operation?.retained || lifecycle.detail) && <details className="app-details mt-2"><summary>处理详情</summary>
        {(operation?.error || lifecycle.detail) && <p className="whitespace-pre-wrap break-words">{operation?.error || lifecycle.detail}</p>}
        {operation?.retained && <p className="break-all">保留的数据副本：{operation.retained}</p>}
        {operation && <p>操作编号：{operation.id}</p>}
      </details>}
    </div>
  );

  return (
    <section className={active ? "flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-ds-bg-neutral-default-default" : "w-full overflow-y-auto px-4 pb-12 pt-6 sm:px-6"}>
      <div className={active ? "flex h-9 shrink-0 items-center justify-between gap-2 border-b border-ds-border-neutral-subtle-default px-2" : "mb-4 flex flex-wrap items-center justify-between gap-3"}>
        <div className="flex min-w-0 items-center gap-2">
          {active && <Button variant="ghost" size="sm" aria-label="返回应用列表" onClick={() => {
            if (!setActiveId(null)) return;
            setLoaded(false);
            window.requestAnimationFrame(() => document.getElementById(`industry-open-${active.id}`)?.focus());
          }}><ArrowLeft className="size-4" />应用列表</Button>}
          <h2 className={active ? "m-0 truncate text-sm font-semibold" : "m-0 text-xl font-semibold"}>{active?.manifest.name || "行业工作台"}</h2>
          {active?.dev_revision && <span className="shrink-0 text-[11px] text-ds-text-neutral-muted-default" title={`开发修订：${active.dev_revision}`}>开发调试</span>}
          {active && active.status !== "ready" && <span className="shrink-0 text-xs text-ds-text-neutral-muted-default">{labels[active.status] || "待处理"}</span>}
        </div>
        {active ? <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="sm" aria-expanded={aiOpen} onClick={() => setAiOpen(value => !value)}>AI 记录{Object.values(aiRecords).some(task => task.origin.app_id === active.id && task.waiting) ? " · 待处理" : Object.values(aiRecords).some(task => task.origin.app_id === active.id && isAppTaskRunning(task)) ? " · 进行中" : ""}</Button>
          {frameSrc && <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" disabled={working} aria-label="页面操作"><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => { if (!leaveIndustryPage()) return; setLoaded(false); setFrameRevision(value => value + 1); }}><RefreshCw className="size-4" />刷新页面</DropdownMenuItem></DropdownMenuContent>
          </DropdownMenu>}
        </div> : <Button variant="primary" disabled={working} onFocus={event => { returnFocus.current = event.currentTarget; }} onClick={() => void choosePackage()}><Upload className="size-4" />安装 ZIP</Button>}
      </div>
      {error && <p role="alert" className="rounded-xl border border-ds-border-neutral-subtle-default p-4 text-sm text-ds-text-error-default-default">{error}</p>}
      {statusPanel}
      {active ? <div className="relative flex min-h-0 flex-1 flex-col">
        {frameSrc ? <div className="relative flex min-h-0 flex-1 flex-col">
          {!loaded && <div className="absolute inset-0 flex items-center justify-center text-sm">正在加载应用…</div>}
          <div inert={working} className={`flex min-h-0 flex-1 flex-col ${working ? "pointer-events-none opacity-60" : ""}`}>
            <iframe key={`${active.generation}-${frameRevision}`} ref={frameRef} src={frameSrc} title={active.manifest.name}
              sandbox="allow-scripts allow-same-origin allow-forms" referrerPolicy="no-referrer"
              className="relative block min-h-0 w-full flex-1 border-0"
              onLoad={() => { setLoaded(true); sendAppearance(); }} />
          </div>
        </div> : <div className="rounded-2xl border border-ds-border-neutral-subtle-default p-6">
          <p>{switching ? "应用切换完成后可继续使用。" : "应用尚未启用，请返回应用列表处理。"}</p>
          {active.error && <p className="break-words text-sm text-ds-text-error-default-default">{active.error}</p>}
        </div>}
        {aiOpen && <IndustryAIPanel appId={active.id} selectedId={aiSelected} onSelect={setAiSelected} onClose={() => setAiOpen(false)} />}
      </div> : apps.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {apps.map(entry => <article key={entry.id} className="flex flex-col rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-4">
          <div className="flex items-center justify-between gap-3"><h3 className="m-0 min-w-0 truncate text-base font-semibold">{entry.manifest.name}</h3>{menu(entry)}</div>
          {entry.manifest.description && <p className="mb-0 mt-2 line-clamp-2 text-sm text-ds-text-neutral-muted-default">{entry.manifest.description}</p>}
          <div className="mt-auto flex items-center justify-between gap-3 pt-2">
            <span className="text-xs text-ds-text-neutral-muted-default">{entry.version || entry.candidate?.version} · {entry.dev_revision && "开发调试 · "}{lifecycle.busy && lifecycle.appId === entry.id ? progress : labels[entry.status] || "待处理"}</span>
            <Button id={`industry-open-${entry.id}`} variant="outline" size="sm" disabled={switching} aria-label={`打开 ${entry.manifest.name}`} onClick={() => { setActiveId(entry.id); setLoaded(false); }}>打开</Button>
          </div>
        </article>)}
      </div> : <div className="flex min-h-60 flex-col items-center justify-center rounded-2xl border border-dashed border-ds-border-neutral-subtle-default text-center">
        <Boxes className="mb-3 size-8 text-ds-text-neutral-muted-default" /><p className="m-0 font-medium">还没有安装行业应用</p><p className="mt-2 text-sm text-ds-text-neutral-muted-default">从可信开发者获取 ZIP 后，在这里安装。</p>
      </div>}

      <dialog ref={dialogRef} onCancel={() => { setPending(null); setConfirmation(null); }} onClose={() => returnFocus.current?.focus()} aria-labelledby="industry-confirm-title"
        className="m-auto max-h-[calc(100vh-2rem)] w-[min(36rem,calc(100vw-2rem))] space-y-3 overflow-y-auto rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-6 text-ds-text-neutral-default-default shadow-xl backdrop:bg-black/40">
        {pending ? <>
          <h3 id="industry-confirm-title" className="m-0 text-lg font-semibold">{pending.details.manifest.name}</h3>
          <p className="text-sm">{pending.details.current_version ? `${pending.details.current_version} → ${pending.details.manifest.version}` : `版本 ${pending.details.manifest.version}`}</p>
          {!!pending.details.skill_names?.length && <p className="text-sm">附带技能：{pending.details.skill_names.join("、")}</p>}
          <p className="text-sm">{pending.details.current_version ? "自动保留更新前的数据；等待当前任务结束后生效。" : "确认后安装并自动启用。"}生效期间，聊天和行业应用会短暂暂停。</p>
          {active && <p className="text-sm font-medium">请先保存页面内容；尚未保存的内容无法自动保留。</p>}
          <p className="text-sm text-ds-text-neutral-muted-default">此应用可在本机运行代码，请仅安装你信任的来源。</p>
          {!!pending.details.manifest.agent_tools?.length && <div className="rounded-lg border border-ds-border-neutral-subtle-default p-3 text-sm">
            <p className="m-0 font-medium">聊天可用的工具</p>
            <ul className="mb-0 pl-4">{pending.details.manifest.agent_tools.map(tool => <li key={tool.name}>{tool.title} · {tool.access === "write" ? "写入，调用时需确认" : "只读"}{pending.details.current_version && !pending.details.previous_tools?.some(old => old.name === tool.name && old.access === tool.access) ? "（新增或权限变化）" : ""}</li>)}</ul>
          </div>}
          <details className="app-details mt-3 text-xs text-ds-text-neutral-muted-default"><summary>包详情</summary>
            {!!pending.details.manifest.capabilities.host_api.length && <p>应用能力：{pending.details.manifest.capabilities.host_api.map(capability => ({ ai: "发起与查看业务 AI", files: "选择文件和打开产物", navigation: "返回业务位置", ui: "未保存内容提醒" } as Record<string, string>)[capability] || capability).join("、")}</p>}
            <p className="break-all">{pending.details.manifest.id} · {pending.details.file_count} 个文件<br />校验值：{pending.details.sha256}</p>
          </details>
          <div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setPending(null)}>取消</Button><Button variant="primary" onClick={() => void installPackage()}>{pending.details.current_version ? "确认更新" : "确认安装"}</Button></div>
        </> : confirmation && <>
          <h3 id="industry-confirm-title" className="m-0 text-lg font-semibold">{actionName} · {confirmation.entry.manifest.name}</h3>
          <p className="text-sm">{confirmation.action === "rollback" ? `将恢复到 ${new Date(confirmation.entry.recovery!.snapshot.created_at).toLocaleString()} 的版本和记录。先保留当前数据副本，不自动合并新旧记录。` : confirmation.action === "remove" ? "移除应用并保留业务数据。重新安装时仍会检查数据兼容性。" : "等待当前工作结束后自动生效。"}</p>
          {active && <p className="text-sm">请先保存页面内容。</p>}
          <div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirmation(null)}>取消</Button><Button variant="primary" onClick={() => void manageApp()}>确认{actionName}</Button></div>
        </>}
      </dialog>
    </section>
  );
}
