import { runtimeCapability } from "./model_capabilities";
import { initModelCatalog, getModelCatalog, refreshModelCatalog } from "./model_catalog";
import { app, BrowserWindow, dialog, ipcMain, Menu, powerSaveBlocker, protocol, screen, session, shell } from "electron";
import type { ChildProcess } from "child_process";
import { readFile } from "fs/promises";
import * as fs from "fs";
import * as path from "path";
import { createHash, randomBytes, randomUUID } from "crypto";
import * as os from "os";

import {
  connectCdpBrowser,
  getCdpBrowsers,
  launchCdpBrowser,
  onCdpPoolChanged,
  removeCdpBrowser,
} from "./cdp";
import { buildPythonEnv, deleteKey, getKey, initKeychain, setKey } from "./keychain";
import { lightweightValidate } from "./model_validate";
import { runtimeModelsPayload, saveModelConnection } from "./model_runtime";
import {
  initModelsStore,
  loadModels,
  removeProfile,
  setActiveId,
  toBackendProvider,
  upsertProfile,
  upsertConnection,
  removeConnection,
  setCompactionRatio,
  type ModelConnection,
  type ModelCategory,
  type ModelProfile,
  type ModelProvider,
} from "./models_store";
import {
  configureKeepAwakeRuntime,
  getKeepAwakeState,
  initKeepAwake,
  releaseKeepAwake,
  restoreKeepAwake,
  setKeepAwakeEnabled,
} from "./keepAwake";
import { startPdfServer, type PdfServer } from "./pdf_server";
import { start, stop as stopPythonBackend, stopAndWait, startMaintenance } from "./python_runner";
import { IndustryLifecycle, JsonPipe, RuntimeState } from "./industry_lifecycle";
import { getPackageVersion, prepareTerminalPython } from "./terminal_venv";
import { startTunnel, type TunnelHandle } from "./tunnel";
import {
  checkForUpdates,
  downloadUpdate,
  getUpdaterStatus,
  initUpdater,
  installUpdate,
} from "./updater";
import {
  fileToDataUrl,
  openPreviewFile,
  readPreviewFileBuffer,
  writePreviewFileBuffer,
} from "./fileReader";
import { isLocalfileAllowed, localfileUrlToFsPath } from "./localfile";
import { serveAppAsset, validAppRequest, publishAppRuntime } from "./industry_apps";
import { BackendProxy, type BackendRequest } from "./backend_proxy";

let backendUrl = "";
let backendProc: ChildProcess | null = null;
let pdfServer: PdfServer | null = null;
let tunnel: TunnelHandle | null = null;
let keepAwakeReleased = false;
const industryToken = randomBytes(32).toString("hex");
const backendProxy = new BackendProxy(() => backendUrl, () => industryToken);
app.on("web-contents-created", (_event, contents) => {
  const owner = contents.id;
  contents.once("destroyed", () => backendProxy.closeOwner(owner));
});

const isDev = !app.isPackaged;
const isE2E = process.env.MY_COWORK_E2E === "1";
const developerControl = isDev && process.env.MY_COWORK_DEV_CONTROL === "1" && typeof process.send === "function";
const developerApp = developerControl && process.env.MY_COWORK_APP_DEV === "1";

// Development checkouts can keep sessions, settings and credentials separate.
if (isDev && process.env.MY_COWORK_USER_DATA_DIR) {
  const isolatedUserData = path.resolve(process.env.MY_COWORK_USER_DATA_DIR);
  fs.mkdirSync(isolatedUserData, { recursive: true });
  app.setPath("userData", isolatedUserData);
  app.setPath("sessionData", isolatedUserData);
}

// Must run before app ready — local HTML preview in <webview>.
protocol.registerSchemesAsPrivileged([
  {
    scheme: "localfile",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      bypassCSP: true,
    },
  },
  {
    scheme: "mycowork-app",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
    },
  },
]);

if (isE2E) {
  app.commandLine.appendSwitch(
    "remote-debugging-port",
    process.env.MY_COWORK_CDP_PORT || "9222",
  );
}

// ── backend lifecycle ────────────────────────────────────────────────────────

let startInFlight: Promise<string> | null = null;
let backendStartController: AbortController | null = null;
// "needs-model" is a normal first-run state, not a failure: the renderer must
// stay usable so the user can reach Settings and save an API key.
type BackendState = "starting" | "ready" | "needs-model" | "failed";
let backendState: BackendState = "starting";
let backendError = "";
const modelToken = randomUUID();
let modelSync: Promise<void> = Promise.resolve();

async function pushModelConfiguration(): Promise<void> {
  const response = await fetch(`${backendUrl}/api/internal/models`, {
    method: "POST", headers: { "content-type": "application/json", "x-model-token": modelToken, "X-MyCowork-Industry-Token": industryToken },
    body: JSON.stringify(await runtimeModelsPayload()), signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error("模型配置已保存，但同步本地服务失败，请重试");
}

function synchronizeModels(): Promise<void> {
  modelSync = modelSync.catch(() => {}).then(async () => {
    if (startInFlight) await startInFlight;
    if (backendUrl) await pushModelConfiguration();
    else if (loadModels().activeId) await startBackend();
  });
  return modelSync;
}

let runningIndustry: RuntimeState | null = null;
const lifecycle = new IndustryLifecycle({
  pipe: () => new JsonPipe(startMaintenance({
    cwd: isDev ? path.join(__dirname, "..", "backend") : process.resourcesPath,
    dev: isDev,
    env: { MY_COWORK_APP_VERSION: getPackageVersion() },
  })),
  running: () => Boolean(backendProc && backendUrl),
  modelReady: async () => Boolean(isE2E || process.env.MY_COWORK_API_KEY || (await buildPythonEnv()).MY_COWORK_API_KEY),
  start: async (token) => { await startBackendOnce(backendStartController?.signal ?? new AbortController().signal, token); },
  stop: async () => {
    await stopAndWait(backendProc);
    backendProc = null;
    backendUrl = "";
  },
  runtime: async (action) => industryBackendRequest("/api/industry-apps/runtime" + (action ? "/" + action : ""), action ? { method: "POST" } : {}) as Promise<RuntimeState>,
  publish: (runtime) => {
    runningIndustry = runtime;
    publishAppRuntime(runtime);
    if (runtime) { backendState = "ready"; backendError = ""; notifyBackendReady(); }
  },
  changed: (status) => {
    if (developerControl && process.connected) process.send?.({ phase: status.phase, message: status.message });
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send("industry:status", status);
    }
  },
});

async function startBackend(): Promise<string> {
  if (startInFlight) return startInFlight;
  const controller = new AbortController();
  backendStartController = controller;
  startInFlight = (async () => {
  if (developerApp) {
    const file = process.env.MY_COWORK_DEV_ZIP!;
    const sha256 = createHash("sha256").update(await readFile(file)).digest("hex");
    await lifecycle.run({ action: "develop", file, sha256 });
  } else await lifecycle.run({ action: "restart" });
  if (!backendUrl) throw new Error(lifecycle.status.message || "后端未就绪");
  return backendUrl;
  })().catch((error) => {
    if (!controller.signal.aborted) {
      backendState = lifecycle.status.phase === "pending_activation" ? "needs-model" : "failed";
      backendError = error instanceof Error ? error.message : String(error);
      if (backendState === "needs-model") { backendError = ""; notifyBackendNeedsModel(); }
      else notifyBackendFailed(backendError);
    }
    throw error;
  }).finally(() => { startInFlight = null; if (backendStartController === controller) backendStartController = null; });
  return startInFlight;
}

async function startBackendOnce(signal: AbortSignal, operationToken?: string): Promise<string> {
  const startedAt = Date.now();
  backendUrl = "";
  backendState = "starting";
  backendError = "";
  for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.webContents.send("backend:starting");
  const env = await buildPythonEnv();
  signal.throwIfAborted();
  console.info(`[backend] configuration ready after ${Date.now() - startedAt} ms`);
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith("MY_COWORK_") && value) {
      env[key] = value;
    }
  }
  env.MY_COWORK_MODEL_TOKEN = modelToken;
  // Prefer bundled OfficeCLI; fall back to user installs on PATH.
  const pathExtras: string[] = [];
  const bundledName =
    process.platform === "win32" ? "officecli.exe" : "officecli";
  const bundledCandidates = [
    // Packaged app
    path.join(process.resourcesPath, "bin", bundledName),
    // Dev: repo resources/bin
    path.join(__dirname, "..", "resources", "bin", bundledName),
  ];
  for (const candidate of bundledCandidates) {
    if (fs.existsSync(candidate)) {
      pathExtras.push(path.dirname(candidate));
      env.MY_COWORK_OFFICECLI = candidate;
      env.MY_COWORK_OFFICECLI_DIR = path.dirname(candidate);
      break;
    }
  }
  const localBin = path.join(os.homedir(), ".local", "bin");
  if (fs.existsSync(localBin)) pathExtras.push(localBin);
  if (process.platform === "win32") {
    const localApp = process.env.LOCALAPPDATA;
    if (localApp) {
      const officeCli = path.join(localApp, "OfficeCli");
      if (fs.existsSync(officeCli)) pathExtras.push(officeCli);
    }
  }
  if (pathExtras.length) {
    const cur = env.PATH || process.env.PATH || "";
    env.PATH = [...pathExtras, cur].join(path.delimiter);
  }
  if (pdfServer) {
    env.ELECTRON_PDF_PORT = String(pdfServer.port);
  }

  const appVersion = getPackageVersion();
  env.MY_COWORK_APP_VERSION = appVersion;
  env.MY_COWORK_INDUSTRY_TOKEN = industryToken;
  if (operationToken) env.MY_COWORK_OPERATION_TOKEN = operationToken;
  else delete env.MY_COWORK_OPERATION_TOKEN;
  // Do not wait for the (first-launch) venv copy — it can take minutes and
  // used to block the window. Backend falls back if python.exe is not ready yet.
  const terminalBase = prepareTerminalPython(appVersion);
  console.info(`[backend] terminal environment checked after ${Date.now() - startedAt} ms`);
  if (terminalBase) {
    env.MY_COWORK_TERMINAL_BASE = terminalBase;
  }

  if (!env.MY_COWORK_API_KEY && !isE2E) {
    // Saving the first usable model starts the backend. Later edits synchronize in place.
    backendState = "needs-model";
    backendError = "";
    notifyBackendNeedsModel();
    return "";
  }

  backendState = "starting";
  const info = await start({
    cwd: isDev
      ? path.join(__dirname, "..", "backend")
      : process.resourcesPath,
    dev: isDev,
    env,
    signal,
    healthTimeoutMs: isE2E ? 60_000 : 90_000,
  });
  backendUrl = info.url;
  backendProc = info.process;
  info.process.once("exit", () => {
    if (backendProc !== info.process) return;
    backendProc = null;
    backendUrl = "";
    runningIndustry = null; publishAppRuntime(null);
    backendState = "failed";
    backendError = "本地服务意外退出，请重试启动";
    notifyBackendFailed(backendError);
  });
  try { if (!isE2E) await pushModelConfiguration(); } catch (error) {
    await stopAndWait(info.process); backendProc = null; backendUrl = ""; throw error;
  }
  backendState = "ready";
  backendError = "";

  return backendUrl;
}

function notifyBackendNeedsModel(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send("backend:needs-model");
  }
}

function notifyBackendReady(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send("backend:ready", backendUrl);
  }
}

function notifyBackendFailed(message: string): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send("backend:failed", message);
  }
}

// ── IPC handlers ─────────────────────────────────────────────────────────────

ipcMain.handle("keychain:get", async (_event, account: string) => {
  return getKey("my-cowork", account);
});

ipcMain.handle("keychain:set", async (_event, account: string, value: string) => {
  await setKey("my-cowork", account, value);
});

ipcMain.handle("models:get", () => loadModels());
ipcMain.handle("models:catalog", () => getModelCatalog());
ipcMain.handle("models:refreshCatalog", async () => {
  const catalog = await refreshModelCatalog();
  await synchronizeModels();
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) window.webContents.send("models:catalogChanged");
  }
  return catalog;
});

ipcMain.handle("models:upsertConnection", async (_event, input: ModelConnection & { apiKey?: string }) => {
  const id = input.id || randomUUID();
  await saveModelConnection({ id, name: input.name, provider: input.provider, baseUrl: input.baseUrl?.trim(),
    category: input.category, presetId: input.presetId, apiKey: input.apiKey });
  await synchronizeModels();
  return loadModels();
});
ipcMain.handle("models:removeConnection", async (_event, id: string) => {
  const account = loadModels().connections?.find(c => c.id === id)?.keyAccount;
  removeConnection(id);
  await synchronizeModels();
  if (account) await deleteKey("my-cowork", account);
  return loadModels();
});
ipcMain.handle("models:compactionRatio", async (_event, ratio: number) => {
  setCompactionRatio(ratio);
  await synchronizeModels();
  return loadModels();
});

ipcMain.handle(
  "models:upsert",
  async (
    _event,
    input: {
      id?: string;
      name: string;
      provider: ModelProvider;
      model: string;
      baseUrl?: string;
      apiKey?: string;
      activate?: boolean;
      isValid?: boolean;
      lastValidatedAt?: string;
      category?: ModelCategory;
      presetId?: string;
      connectionId?: string;
      capabilityId?: string;
    reasoningAdapter?: string;
      reasoning?: ModelProfile["reasoning"];
      contextWindow?: number;
    },
  ) => {
    const id = input.id || randomUUID();
    const existing = loadModels().profiles.find((p) => p.id === id);
    const profile: ModelProfile = {
      id,
      name: input.name.trim(),
      provider: input.provider,
      model: input.model.trim(),
      baseUrl: input.baseUrl?.trim() || undefined,
      isValid: input.isValid ?? existing?.isValid,
      lastValidatedAt: input.lastValidatedAt ?? existing?.lastValidatedAt,
      category: input.category ?? existing?.category,
      presetId: input.presetId ?? existing?.presetId,
      connectionId: input.connectionId ?? existing?.connectionId,
      capabilityId: input.capabilityId,
      reasoningAdapter: input.reasoningAdapter,
      reasoning: input.reasoning,
      contextWindow: input.contextWindow,
    };
    const effectiveConnection = loadModels().connections?.find(c => c.id === profile.connectionId);
    runtimeCapability({ ...profile, provider: effectiveConnection?.provider ?? profile.provider, baseUrl: effectiveConnection?.baseUrl ?? profile.baseUrl }, getModelCatalog());
    if (input.apiKey?.trim()) {
      const connection = loadModels().connections?.find(c => c.id === profile.connectionId);
      await setKey("my-cowork", connection?.keyAccount ?? `model:${id}`, input.apiKey.trim());
    }
    let state = upsertProfile(profile);
    if (input.activate === true) {
      state = setActiveId(id);
    }
    await synchronizeModels();
    return state;
  },
);

ipcMain.handle("models:remove", async (_event, id: string) => {
  removeProfile(id);
  await synchronizeModels();
  return loadModels();
});

ipcMain.handle("models:setActive", async (_event, id: string) => {
  setActiveId(id);
  await synchronizeModels();
  return loadModels();
});

ipcMain.handle(
  "models:validate",
  async (
    _event,
    input: {
      profileId?: string;
      provider: ModelProvider;
      model: string;
      apiKey?: string;
      baseUrl?: string;
    },
  ) => {
    // Prefer Python backend when running.
    if (backendUrl) {
      try {
        const res = await fetch(`${backendUrl}/api/model/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-MyCowork-Industry-Token": industryToken },
          signal: AbortSignal.timeout(30000),
          body: JSON.stringify({
            provider: toBackendProvider(input.provider),
            model: input.model,
            profile_id: input.profileId,
            api_key: input.apiKey ?? "",
            base_url: input.baseUrl,
          }),
        });
        const data = (await res.json()) as {
          ok?: boolean;
          error?: string;
          latency_ms?: number;
        };
        if (res.ok) {
          return {
            ok: !!data.ok,
            error: data.error,
            latency_ms: data.latency_ms,
          };
        }
      } catch {
        // Unsaved drafts may fall through to a connectivity-only Node probe.
      }
    }
    if (input.profileId) return { ok: false, error: "完整参数测试未完成，请确认后端已就绪后重试" };
    return lightweightValidate(input);
  },
);

ipcMain.handle("backend-url", () => backendUrl);

ipcMain.handle("backend:status", () => ({ state: backendState, error: backendError }));

ipcMain.handle("backend:restart", async () => {
  await startBackend();
  return backendUrl;
});

function requireHostWindow(sender: Electron.WebContents, frame?: Electron.WebFrameMain | null): void {
  const win = BrowserWindow.fromWebContents(sender);
  if (!win || win.webContents !== sender || !frame || frame.processId !== sender.mainFrame.processId || frame.routingId !== sender.mainFrame.routingId) {
    throw new Error("industry app operation must come from the host window");
  }
}

ipcMain.handle("backend:request", (event, id: string, request: BackendRequest) => {
  requireHostWindow(event.sender, event.senderFrame);
  return backendProxy.request(event.sender.id, id, request);
});
ipcMain.handle("backend:read", (event, id: string) => {
  requireHostWindow(event.sender, event.senderFrame);
  return backendProxy.read(event.sender.id, id);
});
ipcMain.handle("backend:cancel", (event, id: string) => {
  requireHostWindow(event.sender, event.senderFrame);
  backendProxy.cancel(event.sender.id, id);
});

async function industryBackendRequest(
  endpoint: string,
  options: RequestInit = {},
): Promise<unknown> {
  if (!backendUrl) throw new Error("backend is not ready");
  const headers = new Headers(options.headers);
  headers.set("X-MyCowork-Industry-Token", industryToken);
  const response = await fetch(backendUrl + endpoint, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data
      ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)).slice(0, 2000)
      : "request failed";
    throw new Error(detail);
  }
  return data;
}

ipcMain.handle("industry:list", async (event) => {
  requireHostWindow(event.sender, event.senderFrame);
  const result = await lifecycle.query({ command: "list" });
  result.apps = result.apps.filter((entry: any) => !entry.removed).map((entry: any) => {
    const running = runningIndustry?.apps.find((item) => item.id === entry.id && item.version === entry.version);
    const devUrl = developerApp && running?.dev_revision && entry.id === process.env.MY_COWORK_DEV_APP_ID && /^http:\/\/127\.0\.0\.1:[0-9]+$/.test(process.env.MY_COWORK_DEV_URL || "") ? process.env.MY_COWORK_DEV_URL : undefined;
    return { ...entry, status: running?.status || (entry.status === "ready" ? "pending_activation" : entry.status), generation: running ? runningIndustry?.generation : undefined, ...(devUrl ? { dev_url: devUrl } : {}) };
  });
  return { ...result, lifecycle: lifecycle.status };
});

ipcMain.handle("industry:status", (event) => {
  requireHostWindow(event.sender, event.senderFrame);
  return lifecycle.status;
});
ipcMain.handle("industry:cancel", (event) => {
  requireHostWindow(event.sender, event.senderFrame);
  lifecycle.cancel();
});
ipcMain.handle("industry:inspect", async (event, filePath: string) => {
  requireHostWindow(event.sender, event.senderFrame);
  if (path.extname(filePath).toLowerCase() !== ".zip") throw new Error("select a .zip file");
  return lifecycle.query({ command: "inspect", file: filePath });
});

ipcMain.handle("industry:install", async (event, filePath: string, expectedSha256: string) => {
  requireHostWindow(event.sender, event.senderFrame);
  if (path.extname(filePath).toLowerCase() !== ".zip") throw new Error("select a .zip file");
  if (!/^[0-9a-f]{64}$/.test(expectedSha256)) throw new Error("invalid package hash");
  return lifecycle.run({ action: "install", file: filePath, sha256: expectedSha256 });
});

ipcMain.handle(
  "industry:request",
  async (
    event,
    appId: string,
    method: string,
    requestPath: string,
    body?: unknown,
    generation?: string,
  ) => {
    requireHostWindow(event.sender, event.senderFrame);
    if (lifecycle.status.busy || !runningIndustry || generation !== runningIndustry.generation) throw new Error("应用正在更新，请稍后重新打开页面");
    if (!runningIndustry.apps.some((item) => item.id === appId && item.status === "ready")) throw new Error("应用未启用");
    if (!validAppRequest(appId, method, requestPath)) throw new Error("invalid app request");
    return industryBackendRequest("/api/apps/" + appId + requestPath, {
      method,
      headers: { "Content-Type": "application/json" },
      body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
    });
  },
);

ipcMain.handle("industry:manage", async (event, appId: string, action: string) => {
  requireHostWindow(event.sender, event.senderFrame);
  if (!/^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$/.test(appId)) throw new Error("invalid app id");
  if (!["disable", "enable", "rollback", "remove", "retry"].includes(action)) throw new Error("invalid app action");
  return lifecycle.run({ action, app_id: appId });
});

ipcMain.handle("print-to-pdf", async (_event, html: string) => {
  if (!pdfServer) {
    return Buffer.from("");
  }
  const res = await fetch(`http://127.0.0.1:${pdfServer.port}/print-to-pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });
  if (!res.ok) {
    throw new Error(`print-to-pdf failed: ${res.status}`);
  }
  return Buffer.from(await res.arrayBuffer());
});

ipcMain.handle("open-path", async (_event, filePath: string) => {
  if (filePath) {
    const error = await shell.openPath(filePath);
    if (error) throw new Error(error);
  }
});

ipcMain.handle("dialog:select-directory", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  return result.filePaths[0];
});

ipcMain.handle("dialog:select-files", async (_event, options?: { title?: string }) => {
  const result = await dialog.showOpenDialog({
    title: options?.title || "选择文件",
    properties: ["openFile", "multiSelections"],
    filters: [{ name: "所有文件", extensions: ["*"] }],
  });
  if (result.canceled || !result.filePaths.length) {
    return { success: false, canceled: true, files: [] };
  }
  const files = result.filePaths.map((filePath) => ({
    filePath,
    fileName: filePath.split(/[/\\]/).pop() || filePath,
  }));
  return { success: true, files, fileCount: files.length };
});

ipcMain.handle("read-text-file", async (_event, filePath: string) => {
  if (!filePath) return { error: "empty path" };
  try {
    const text = await readFile(filePath, "utf8");
    const max = 200_000;
    return {
      content: text.length > max ? `${text.slice(0, max)}\n…(truncated)` : text,
    };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
});

/** Eigent: open-file — office/csv → HTML; md/html/text → string; pdf → path. */
ipcMain.handle(
  "open-file",
  async (_event, type: string, filePath: string, _showSource?: boolean) => {
    return openPreviewFile(type || "", filePath);
  },
);

/** Eigent: read-file-dataurl — PDF/images for iframe/img. */
ipcMain.handle("read-file-dataurl", async (_event, filePath: string) => {
  return fileToDataUrl(filePath);
});

/** Binary read for docx-preview / SheetJS (Uint8Array via structured clone). */
ipcMain.handle("read-file-buffer", async (_event, filePath: string) => {
  try {
    return { ok: true as const, data: readPreviewFileBuffer(filePath) };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : String(e),
    };
  }
});

/** Binary write for spreadsheet save / save-as. */
ipcMain.handle(
  "write-file-buffer",
  async (
    _event,
    filePath: string,
    data: Uint8Array,
    options?: { allowCreate?: boolean },
  ) => {
    try {
      writePreviewFileBuffer(filePath, data, options);
      return { ok: true as const };
    } catch (e) {
      return {
        ok: false as const,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
);

ipcMain.handle(
  "dialog:save-file",
  async (
    _event,
    options?: {
      defaultPath?: string;
      filters?: Array<{ name: string; extensions: string[] }>;
    },
  ) => {
    const result = await dialog.showSaveDialog({
      defaultPath: options?.defaultPath,
      filters: options?.filters?.length
        ? options.filters
        : [{ name: "所有文件", extensions: ["*"] }],
    });
    if (result.canceled || !result.filePath) {
      return { canceled: true as const };
    }
    return { canceled: false as const, filePath: result.filePath };
  },
);

ipcMain.handle("tunnel:start", async () => {
  if (!backendUrl) {
    throw new Error("Backend is not running");
  }
  if (tunnel) {
    return `${tunnel.url}/webhook/lark`;
  }
  tunnel = await startTunnel(backendUrl);
  return `${tunnel.url}/webhook/lark`;
});

ipcMain.handle("tunnel:stop", async () => {
  tunnel?.stop();
  tunnel = null;
});

ipcMain.handle("tunnel:url", () => (tunnel ? `${tunnel.url}/webhook/lark` : null));

ipcMain.handle("cdp:list", () => getCdpBrowsers());
ipcMain.handle("cdp:launch", () => launchCdpBrowser());
ipcMain.handle("cdp:connect", (_e, port: number) => connectCdpBrowser(port));
ipcMain.handle("cdp:remove", (_e, id: string) => removeCdpBrowser(id));
ipcMain.handle("updater:status", () => getUpdaterStatus());
ipcMain.handle("updater:check", () => checkForUpdates());
ipcMain.handle("updater:download", () => downloadUpdate());
ipcMain.handle("updater:install", async () => {
  if (lifecycle.status.busy) return { ok: false, message: "请等待行业应用操作完成后再重启更新" };
  if (getUpdaterStatus().state !== "downloaded") {
    return { ok: false, message: "no update downloaded" };
  }
  backendStartController?.abort();
  if (backendProc) {
    stopPythonBackend(backendProc);
    backendProc = null;
  }
  keepAwakeReleased = true;
  try {
    await releaseKeepAwake();
  } catch (err) {
    console.error("Failed to release keep-awake before update:", err);
  }
  return installUpdate();
});

ipcMain.handle("keepAwake:get", () => getKeepAwakeState());
ipcMain.handle(
  "keepAwake:set",
  (_e, body: { enabled?: boolean } | boolean | undefined) => {
    const enabled =
      typeof body === "boolean" ? body : Boolean(body?.enabled);
    return setKeepAwakeEnabled(enabled);
  },
);

// ── window ───────────────────────────────────────────────────────────────────

async function loadRenderer(win: BrowserWindow) {
  const forceFile = isE2E || developerControl;
  if (isDev && !forceFile) {
    const devServerUrl = process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5174";
    await win.loadURL(devServerUrl);
  } else {
    await win.loadFile(path.join(__dirname, "..", "dist-renderer", "index.html"));
  }
}

async function createWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  const ww = Math.min(1440, Math.floor(sw * 0.9));
  const wh = Math.min(900, Math.floor(sh * 0.9));

  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, "icon.ico")
    : path.join(__dirname, "..", "build", "icon.ico");
  const win = new BrowserWindow({
    width: ww,
    height: wh,
    title: "MyCowork",
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#f6f7ff",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });
  win.once("ready-to-show", () => {
    if (!win.isDestroyed()) win.show();
  });

  await loadRenderer(win);
  if (!win.isDestroyed() && !win.isVisible()) win.show();
}

// ── startup ──────────────────────────────────────────────────────────────────

// Only the CLI-owned Node IPC channel can control a developer session.
if (developerControl) {
  let quitting = false;
  process.on("message", async (message: { command?: string }) => {
    try {
      if (message.command === "cancel") lifecycle.cancel();
      else if (["reload", "restart"].includes(message.command || "") && !quitting) await startBackend();
      else if (message.command === "quit" && !quitting) {
        quitting = true;
        lifecycle.cancel();
        while (lifecycle.status.busy) await new Promise(resolve => setTimeout(resolve, 300));
        if (backendUrl) {
          let state = await industryBackendRequest("/api/industry-apps/runtime/drain", { method: "POST" }) as RuntimeState;
          while (state.active > 0) {
            if (process.connected) process.send?.({ phase: "draining", message: `等待 ${state.active} 项工作结束；仍可在工作台回答或停止任务。` });
            await new Promise(resolve => setTimeout(resolve, 300));
            state = await industryBackendRequest("/api/industry-apps/runtime") as RuntimeState;
          }
        }
        await stopAndWait(backendProc);
        backendProc = null; backendUrl = "";
        if (developerApp) await lifecycle.query({ command: "collect_development" }).catch(error => console.warn("开发快照清理未完成，已保留：", error));
        for (const win of BrowserWindow.getAllWindows()) win.destroy();
        app.quit();
      }
    } catch (error) {
      console.error("开发操作失败：", error);
      if (process.connected) process.send?.({ phase: "failed", message: "开发操作未完成，请查看工作台状态与日志。" });
      quitting = false;
      if (message.command === "quit") {
        // A failed drain cannot leave the CLI waiting forever. Stop only this
        // instance; ordinary startup recovery handles any interrupted work.
        await stopAndWait(backendProc).catch(error => console.error("停止开发后端失败：", error));
        backendProc = null; backendUrl = "";
        for (const win of BrowserWindow.getAllWindows()) win.destroy();
        app.quit();
      }
    } finally {
      if (process.connected && ["reload", "restart"].includes(message.command || "")) process.send?.({ done: true });
    }
  });
  process.once("disconnect", () => {
    for (const win of BrowserWindow.getAllWindows()) win.destroy();
    app.quit();
  });
}

function registerLocalfileProtocol(): void {
  const handler = async (request: Request): Promise<Response> => {
    const filePath = localfileUrlToFsPath(request.url);
    const allowed = [os.homedir(), app.getPath("userData"), app.getPath("temp")];
    if (!isLocalfileAllowed(filePath, allowed)) {
      console.warn("[localfile] forbidden:", filePath, "from", request.url);
      return new Response("Forbidden", { status: 403 });
    }
    try {
      const data = await readFile(filePath);
      const ext = path.extname(filePath).toLowerCase();
      const mime: Record<string, string> = {
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
      };
      return new Response(data, {
        status: 200,
        headers: {
          "Content-Type": mime[ext] || "application/octet-stream",
          "Content-Length": String(data.byteLength),
        },
      });
    } catch (err) {
      console.warn("[localfile] missing:", filePath, err);
      return new Response("File Not Found", { status: 404 });
    }
  };
  protocol.handle("localfile", handler);
  // Preview <webview> uses partition persist:session-preview
  try {
    session
      .fromPartition("persist:session-preview")
      .protocol.handle("localfile", handler);
  } catch (err) {
    console.warn("localfile protocol on preview partition:", err);
  }
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  registerLocalfileProtocol();
  protocol.handle("mycowork-app", (request) => serveAppAsset(request.url));
  const userData = app.getPath("userData");
  initKeychain(userData, developerControl ? process.env.MY_COWORK_CREDENTIAL_SCOPE : undefined);
  initModelsStore(userData);
  initModelCatalog(userData);
  configureKeepAwakeRuntime({ powerSaveBlocker });
  initKeepAwake(userData);
  try {
    await restoreKeepAwake();
  } catch (err) {
    console.error("Failed to restore keep-awake:", err);
  }

  const windowReady = createWindow();
  try {
    pdfServer = await startPdfServer();
  } catch (err) {
    console.error("Failed to start PDF server:", err);
    pdfServer = null;
  }
  await windowReady;

  const bootBackend = () =>
    startBackend().catch((err) => {
      console.error("Failed to start backend:", err);
    });
  // Packaged Python can take tens of seconds (PyInstaller + health). Show UI first.
  if (isE2E) {
    await bootBackend();
  } else {
    void bootBackend();
  }

  initUpdater();
  onCdpPoolChanged((list) => {
    for (const w of BrowserWindow.getAllWindows()) {
      w.webContents.send("cdp:pool-changed", list);
    }
  });
});

app.on("before-quit", (event) => {
  backendStartController?.abort();
  if (backendProc) {
    stopPythonBackend(backendProc);
    backendProc = null;
  }
  if (keepAwakeReleased) return;
  event.preventDefault();
  void releaseKeepAwake()
    .catch((err) => {
      console.error("Failed to release keep-awake:", err);
    })
    .finally(() => {
      keepAwakeReleased = true;
      app.quit();
    });
});

// The dev supervisor sends SIGTERM on POSIX; route it through owned cleanup.
process.on("SIGINT", () => app.quit());
process.on("SIGTERM", () => app.quit());

app.on("window-all-closed", () => {
  backendStartController?.abort();
  tunnel?.stop();
  tunnel = null;
  if (backendProc) {
    stopPythonBackend(backendProc);
    backendProc = null;
  }
  void pdfServer?.close();
  app.quit();
});
