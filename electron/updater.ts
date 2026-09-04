/**
 * electron-updater wiring for GitHub Releases.
 * Loaded lazily so a missing packaged dependency cannot crash app startup.
 */
import { app, BrowserWindow } from "electron";
import type { UpdateInfo } from "electron-updater";

type AutoUpdater = typeof import("electron-updater").autoUpdater;

export type UpdaterState =
  | "idle"
  | "checking"
  | "available"
  | "not-available"
  | "downloading"
  | "downloaded"
  | "error";

export interface UpdaterStatus {
  state: UpdaterState;
  currentVersion: string;
  availableVersion?: string;
  percent?: number;
  totalSize?: number;
  message?: string;
}

let wired = false;
let status: UpdaterStatus = { state: "idle", currentVersion: "" };

function loadAutoUpdater(): AutoUpdater | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("electron-updater").autoUpdater as AutoUpdater;
  } catch (err) {
    console.error("electron-updater not available:", err);
    return null;
  }
}

function currentVersion(): string {
  try {
    return app.getVersion();
  } catch {
    return "";
  }
}

function fileSize(info?: UpdateInfo): number | undefined {
  const files = info?.files;
  if (!files?.length) return undefined;
  const total = files.reduce((sum, file) => sum + (file.size || 0), 0);
  return total > 0 ? total : undefined;
}

function snapshot(): UpdaterStatus {
  return { ...status, currentVersion: currentVersion() };
}

function setStatus(patch: Partial<UpdaterStatus>): UpdaterStatus {
  status = { ...snapshot(), ...patch };
  const next = snapshot();
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send("updater:status", next);
  }
  return next;
}

function wire(autoUpdater: AutoUpdater): void {
  if (wired) return;
  wired = true;
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on("checking-for-update", () => {
    setStatus({ state: "checking", message: undefined });
  });
  autoUpdater.on("update-available", (info) => {
    setStatus({
      state: "available",
      availableVersion: info.version,
      totalSize: fileSize(info),
      percent: undefined,
      message: undefined,
    });
  });
  autoUpdater.on("update-not-available", () => {
    setStatus({
      state: "not-available",
      availableVersion: undefined,
      totalSize: undefined,
      percent: undefined,
      message: undefined,
    });
  });
  autoUpdater.on("download-progress", (progress) => {
    setStatus({
      state: "downloading",
      percent: progress.percent,
      totalSize: progress.total || status.totalSize,
      message: undefined,
    });
  });
  autoUpdater.on("update-downloaded", (info) => {
    setStatus({
      state: "downloaded",
      availableVersion: info.version,
      percent: 100,
      totalSize: fileSize(info) ?? status.totalSize,
      message: undefined,
    });
  });
  autoUpdater.on("error", (err) => {
    console.error("updater error:", err);
    setStatus({
      state: "error",
      message: err instanceof Error ? err.message : String(err),
    });
  });
}

export function getUpdaterStatus(): UpdaterStatus {
  return snapshot();
}

export function initUpdater(): void {
  if (!app.isPackaged) {
    setStatus({ state: "idle", message: "dev-skip" });
    return;
  }
  const autoUpdater = loadAutoUpdater();
  if (!autoUpdater) {
    setStatus({ state: "error", message: "updater module missing" });
    return;
  }
  try {
    wire(autoUpdater);
    void autoUpdater.checkForUpdates().catch((err) => {
      console.error("checkForUpdates failed:", err);
    });
  } catch (err) {
    console.error("initUpdater failed:", err);
    setStatus({
      state: "error",
      message: err instanceof Error ? err.message : String(err),
    });
  }
}

export async function checkForUpdates(): Promise<UpdaterStatus> {
  if (!app.isPackaged) {
    return setStatus({ state: "idle", message: "dev-skip" });
  }
  const autoUpdater = loadAutoUpdater();
  if (!autoUpdater) {
    return setStatus({ state: "error", message: "updater module missing" });
  }
  try {
    wire(autoUpdater);
    setStatus({ state: "checking", message: undefined });
    await autoUpdater.checkForUpdates();
    return snapshot();
  } catch (e) {
    return setStatus({
      state: "error",
      message: e instanceof Error ? e.message : String(e),
    });
  }
}

export async function downloadUpdate(): Promise<UpdaterStatus> {
  if (!app.isPackaged) {
    return setStatus({ state: "idle", message: "dev-skip" });
  }
  const autoUpdater = loadAutoUpdater();
  if (!autoUpdater) {
    return setStatus({ state: "error", message: "updater module missing" });
  }
  try {
    wire(autoUpdater);
    setStatus({ state: "downloading", percent: status.percent ?? 0, message: undefined });
    await autoUpdater.downloadUpdate();
    return snapshot();
  } catch (e) {
    return setStatus({
      state: "error",
      message: e instanceof Error ? e.message : String(e),
    });
  }
}

export function installUpdate(): { ok: boolean; message?: string } {
  if (!app.isPackaged) {
    return { ok: false, message: "dev-skip" };
  }
  if (status.state !== "downloaded") {
    return { ok: false, message: "no update downloaded" };
  }
  const autoUpdater = loadAutoUpdater();
  if (!autoUpdater) {
    return { ok: false, message: "updater module missing" };
  }
  autoUpdater.quitAndInstall(false, true);
  return { ok: true };
}
