/**
 * Adapted from eigent electron/main/update.ts (electron-updater wiring).
 */
import { app } from "electron";
import { autoUpdater } from "electron-updater";

export function initUpdater(): void {
  if (!app.isPackaged) return;
  try {
    autoUpdater.autoDownload = false;
    autoUpdater.on("error", (err) => {
      console.error("updater error:", err);
    });
    void autoUpdater.checkForUpdates().catch((err) => {
      console.error("checkForUpdates failed:", err);
    });
  } catch (err) {
    console.error("initUpdater failed:", err);
  }
}

export async function checkForUpdates(): Promise<{ ok: boolean; message: string }> {
  if (!app.isPackaged) {
    return { ok: true, message: "dev mode: updater skipped" };
  }
  try {
    const result = await autoUpdater.checkForUpdates();
    return {
      ok: true,
      message: result?.updateInfo?.version
        ? `update available: ${result.updateInfo.version}`
        : "no update",
    };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}
