/**
 * Adapted from eigent electron CDP browser pool (minimal local implementation).
 */
import { spawn, type ChildProcess } from "child_process";
import { existsSync } from "fs";
import * as os from "os";
import * as path from "path";
import { randomUUID } from "crypto";

export interface CdpBrowser {
  id: string;
  port: number;
  name?: string;
  isExternal: boolean;
  addedAt: number;
  pid?: number;
}

const browsers = new Map<string, CdpBrowser & { proc?: ChildProcess }>();
let nextPort = 9222;
const listeners = new Set<(list: CdpBrowser[]) => void>();

function snapshot(): CdpBrowser[] {
  return [...browsers.values()].map(({ proc: _p, ...rest }) => rest);
}

function emit() {
  const list = snapshot();
  for (const cb of listeners) cb(list);
}

export function onCdpPoolChanged(cb: (list: CdpBrowser[]) => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function getCdpBrowsers(): CdpBrowser[] {
  return snapshot();
}

function chromePath(): string | null {
  const platform = process.platform;
  const candidates =
    platform === "darwin"
      ? [
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
          "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
      : platform === "win32"
        ? [
            path.join(process.env.PROGRAMFILES || "", "Google/Chrome/Application/chrome.exe"),
            path.join(process.env["PROGRAMFILES(X86)"] || "", "Google/Chrome/Application/chrome.exe"),
          ]
        : ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"];
  return candidates.find((p) => p && existsSync(p)) || null;
}

export async function launchCdpBrowser(): Promise<{ port?: number; error?: string; id?: string }> {
  const bin = chromePath();
  if (!bin) return { error: "Chrome/Chromium not found" };
  const port = nextPort++;
  const userData = path.join(os.tmpdir(), `my-cowork-cdp-${port}`);
  try {
    const proc = spawn(
      bin,
      [
        `--remote-debugging-port=${port}`,
        `--user-data-dir=${userData}`,
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
      ],
      { stdio: "ignore", detached: false },
    );
    const id = randomUUID();
    browsers.set(id, {
      id,
      port,
      name: `Chrome :${port}`,
      isExternal: false,
      addedAt: Date.now(),
      pid: proc.pid,
      proc,
    });
    proc.on("exit", () => {
      browsers.delete(id);
      emit();
    });
    emit();
    return { port, id };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

export async function connectCdpBrowser(
  port: number,
): Promise<{ success?: boolean; error?: string; id?: string }> {
  if (![...browsers.values()].some((b) => b.port === port)) {
    const id = randomUUID();
    browsers.set(id, {
      id,
      port,
      name: `External :${port}`,
      isExternal: true,
      addedAt: Date.now(),
    });
    emit();
    return { success: true, id };
  }
  return { success: true };
}

export async function removeCdpBrowser(
  id: string,
): Promise<{ success: boolean; error?: string }> {
  const b = browsers.get(id);
  if (!b) return { success: false, error: "not found" };
  try {
    b.proc?.kill();
  } catch {
    /* ignore */
  }
  browsers.delete(id);
  emit();
  return { success: true };
}
