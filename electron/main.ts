import { app, BrowserWindow, dialog, ipcMain, Menu, powerSaveBlocker, protocol, screen, session, shell } from "electron";
import type { ChildProcess } from "child_process";
import { readFile } from "fs/promises";
import * as fs from "fs";
import * as path from "path";
import { randomUUID } from "crypto";
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
import {
  initModelsStore,
  loadModels,
  removeProfile,
  setActiveId,
  toBackendProvider,
  upsertProfile,
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
import { start, stop as stopPythonBackend } from "./python_runner";
import { getPackageVersion, prepareTerminalPython } from "./terminal_venv";
import { startTunnel, type TunnelHandle } from "./tunnel";
import { checkForUpdates, initUpdater } from "./updater";
import {
  fileToDataUrl,
  openPreviewFile,
  readPreviewFileBuffer,
  writePreviewFileBuffer,
} from "./fileReader";
import { isLocalfileAllowed, localfileUrlToFsPath } from "./localfile";

let backendUrl = "";
let backendProc: ChildProcess | null = null;
let pdfServer: PdfServer | null = null;
let tunnel: TunnelHandle | null = null;

const isDev = !app.isPackaged;
const isE2E = process.env.MY_COWORK_E2E === "1";

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
]);

if (isE2E) {
  app.commandLine.appendSwitch(
    "remote-debugging-port",
    process.env.MY_COWORK_CDP_PORT || "9222",
  );
}

// ── backend lifecycle ────────────────────────────────────────────────────────

async function startBackend(): Promise<string> {
  if (backendProc) {
    stopPythonBackend(backendProc);
    backendProc = null;
  }
  backendUrl = "";

  const env = await buildPythonEnv();
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith("MY_COWORK_") && value) {
      env[key] = value;
    }
  }
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
  const terminalBase = prepareTerminalPython(appVersion);
  if (terminalBase) {
    env.MY_COWORK_TERMINAL_BASE = terminalBase;
  }

  if (!env.MY_COWORK_API_KEY && !isE2E) {
    throw new Error("MY_COWORK_API_KEY is not set; add a model with API Key in Settings first.");
  }

  const info = await start({
    cwd: path.join(__dirname, "..", "backend"),
    dev: isDev,
    env,
    healthTimeoutMs: isE2E ? 60_000 : undefined,
  });
  backendUrl = info.url;
  backendProc = info.process;
  return backendUrl;
}

async function applyModelAndRestart(): Promise<string> {
  try {
    return await startBackend();
  } catch (err) {
    console.error("Failed to restart backend after model change:", err);
    throw err;
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
    };
    let state = upsertProfile(profile);
    if (input.apiKey?.trim()) {
      await setKey("my-cowork", `model:${id}`, input.apiKey.trim());
    }
    if (input.activate !== false) {
      state = setActiveId(id);
      // Don't block the renderer on backend restart — it can take seconds to
      // minutes (venv prep + uvicorn startup + 15s health check). The profile
      // and key are already persisted; chat will work once the new backend is up.
      void applyModelAndRestart().catch((err) => {
        console.error("Background backend restart failed:", err);
      });
    }
    return state;
  },
);

ipcMain.handle("models:remove", async (_event, id: string) => {
  await deleteKey("my-cowork", `model:${id}`);
  const state = removeProfile(id);
  if (state.activeId) {
    try {
      await applyModelAndRestart();
    } catch {
      // Active profile may lack a key; leave URL empty.
    }
  } else {
    if (backendProc) {
      stopPythonBackend(backendProc);
      backendProc = null;
    }
    backendUrl = "";
  }
  return state;
});

ipcMain.handle("models:setActive", async (_event, id: string) => {
  const state = setActiveId(id);
  // Fire-and-forget restart; see models:upsert for rationale.
  void applyModelAndRestart().catch((err) => {
    console.error("Background backend restart failed:", err);
  });
  return state;
});

ipcMain.handle(
  "models:validate",
  async (
    _event,
    input: {
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
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: toBackendProvider(input.provider),
            model: input.model,
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
        // Fall through to Node probe.
      }
    }
    return lightweightValidate(input);
  },
);

ipcMain.handle("backend-url", () => backendUrl);

ipcMain.handle("backend:restart", async () => {
  await startBackend();
  return backendUrl;
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
  if (filePath) await shell.openPath(filePath);
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
ipcMain.handle("updater:check", () => checkForUpdates());

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
  const forceFile = isE2E;
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

  const win = new BrowserWindow({
    width: ww,
    height: wh,
    title: "MyCowork",
    titleBarStyle: "hiddenInset",
    backgroundColor: "#f6f7ff",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });

  await loadRenderer(win);
}

// ── startup ──────────────────────────────────────────────────────────────────

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
  const userData = app.getPath("userData");
  initKeychain(userData);
  initModelsStore(userData);
  configureKeepAwakeRuntime({ powerSaveBlocker });
  initKeepAwake(userData);
  try {
    await restoreKeepAwake();
  } catch (err) {
    console.error("Failed to restore keep-awake:", err);
  }

  try {
    pdfServer = await startPdfServer();
  } catch (err) {
    console.error("Failed to start PDF server:", err);
    pdfServer = null;
  }

  if (isE2E) {
    await createWindow();
  }

  try {
    await startBackend();
  } catch (err) {
    console.error("Failed to start backend:", err);
    backendUrl = "";
  }

  if (!isE2E) {
    await createWindow();
  }

  initUpdater();
  onCdpPoolChanged((list) => {
    for (const w of BrowserWindow.getAllWindows()) {
      w.webContents.send("cdp:pool-changed", list);
    }
  });
});

let keepAwakeReleased = false;

app.on("before-quit", (event) => {
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

app.on("window-all-closed", () => {
  tunnel?.stop();
  tunnel = null;
  if (backendProc) {
    stopPythonBackend(backendProc);
    backendProc = null;
  }
  void pdfServer?.close();
  app.quit();
});
