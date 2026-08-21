/**
 * Cross-platform keep-awake, adapted from AionUi SystemKeepAwakeController:
 * macOS `caffeinate -dis`, Linux `systemd-inhibit`, Windows
 * SetThreadExecutionState via Electron powerSaveBlocker.
 */

import { spawn, type ChildProcess, type SpawnOptions } from "child_process";
import * as fs from "fs";
import * as path from "path";

export type PowerSaveBlockerType =
  | "prevent-app-suspension"
  | "prevent-display-sleep";

export interface PowerSaveBlockerApi {
  start(type: PowerSaveBlockerType): number;
  stop(id: number): boolean;
}

export type SpawnFn = (
  command: string,
  args: string[],
  options: SpawnOptions,
) => ChildProcess;

export interface KeepAwakeRuntime {
  spawn: SpawnFn;
  platform: () => NodeJS.Platform | string;
  powerSaveBlocker?: PowerSaveBlockerApi;
}

export interface KeepAwakeRuntime {
  spawn: SpawnFn;
  platform: () => NodeJS.Platform | string;
  powerSaveBlocker?: PowerSaveBlockerApi;
}

export interface KeepAwakeState {
  enabled: boolean;
  supported: boolean;
}

export interface KeepAwakeResult {
  ok: boolean;
  enabled: boolean;
  error?: string;
}

const LINUX_WHY = "MyCowork keep-awake is enabled";

let _filePath = "";
let _child: ChildProcess | null = null;
let _displayBlockerId: number | null = null;
let _appBlockerId: number | null = null;
let _runtime: KeepAwakeRuntime = {
  spawn: (cmd, args, opts) => spawn(cmd, args, opts ?? { stdio: "ignore" }),
  platform: () => process.platform,
};

export function keepAwakeSpawnSpec(
  platform: string,
): { cmd: string; args: string[] } | null {
  if (platform === "darwin") {
    return { cmd: "caffeinate", args: ["-dis"] };
  }
  if (platform === "linux") {
    return {
      cmd: "systemd-inhibit",
      args: [
        "--what=sleep",
        `--why=${LINUX_WHY}`,
        "--mode=block",
        "sleep",
        "infinity",
      ],
    };
  }
  return null;
}

export function isKeepAwakeSupported(platform: string): boolean {
  return platform === "darwin" || platform === "linux" || platform === "win32";
}

export function configureKeepAwakeRuntime(
  next: Partial<KeepAwakeRuntime>,
): void {
  _runtime = { ..._runtime, ...next };
}

export function initKeepAwake(userDataPath: string): void {
  _filePath = path.join(userDataPath, "keep-awake.json");
}

export function loadKeepAwakePreference(): boolean {
  if (!_filePath) return false;
  try {
    const raw = JSON.parse(fs.readFileSync(_filePath, "utf8")) as {
      enabled?: unknown;
    };
    return raw.enabled === true;
  } catch {
    return false;
  }
}

export function saveKeepAwakePreference(enabled: boolean): void {
  if (!_filePath) return;
  fs.mkdirSync(path.dirname(_filePath), { recursive: true });
  fs.writeFileSync(
    _filePath,
    JSON.stringify({ enabled }, null, 2) + "\n",
    { mode: 0o600 },
  );
}

function assertionHeld(): boolean {
  return _child != null || _displayBlockerId != null || _appBlockerId != null;
}

export function getKeepAwakeState(): KeepAwakeState {
  return {
    enabled: assertionHeld(),
    supported: isKeepAwakeSupported(String(_runtime.platform())),
  };
}

async function persistOrRollback(
  enabled: boolean,
  previousHeld: boolean,
): Promise<void> {
  try {
    saveKeepAwakePreference(enabled);
  } catch (err) {
    if (previousHeld !== assertionHeld()) {
      await applyAssertion(previousHeld).catch(() => undefined);
    }
    throw err;
  }
}

async function spawnAssertion(
  spec: { cmd: string; args: string[] },
): Promise<ChildProcess> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const child = _runtime.spawn(spec.cmd, spec.args, { stdio: "ignore" });
    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      reject(err);
    };
    const ok = () => {
      if (settled) return;
      settled = true;
      child.off("error", fail);
      resolve(child);
    };
    child.once("error", fail);
    child.once("spawn", ok);
  });
}

function killChild(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        /* already gone */
      }
      resolve();
    }, 2000);
    child.once("exit", done);
    child.once("close", done);
    try {
      child.kill();
    } catch {
      done();
    }
  });
}

async function applyAssertion(enabled: boolean): Promise<void> {
  if (enabled) {
    if (assertionHeld()) return;
    const platform = String(_runtime.platform());
    if (!isKeepAwakeSupported(platform)) {
      throw new Error("Keep-awake is not supported on this platform");
    }
    if (platform === "win32") {
      const blocker = _runtime.powerSaveBlocker;
      if (!blocker) {
        throw new Error("Windows keep-awake requires powerSaveBlocker");
      }
      const displayId = blocker.start("prevent-display-sleep");
      try {
        const appId = blocker.start("prevent-app-suspension");
        _displayBlockerId = displayId;
        _appBlockerId = appId;
      } catch (err) {
        try {
          blocker.stop(displayId);
        } catch {
          /* ignore */
        }
        throw err;
      }
      return;
    }
    const spec = keepAwakeSpawnSpec(platform);
    if (!spec) {
      throw new Error("Keep-awake is not supported on this platform");
    }
    const child = await spawnAssertion(spec);
    child.once("exit", () => {
      if (_child === child) _child = null;
    });
    _child = child;
    return;
  }

  const child = _child;
  _child = null;
  if (child) {
    await killChild(child);
  }
  const blocker = _runtime.powerSaveBlocker;
  if (_displayBlockerId != null && blocker) {
    try {
      blocker.stop(_displayBlockerId);
    } catch {
      /* ignore */
    }
    _displayBlockerId = null;
  }
  if (_appBlockerId != null && blocker) {
    try {
      blocker.stop(_appBlockerId);
    } catch {
      /* ignore */
    }
    _appBlockerId = null;
  }
}

export async function setKeepAwakeEnabled(
  enabled: boolean,
): Promise<KeepAwakeResult> {
  const previousHeld = assertionHeld();
  try {
    await applyAssertion(enabled);
  } catch (err) {
    _child = null;
    _displayBlockerId = null;
    _appBlockerId = null;
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, enabled: assertionHeld(), error: message };
  }
  try {
    await persistOrRollback(enabled, previousHeld);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, enabled: assertionHeld(), error: message };
  }
  return { ok: true, enabled: assertionHeld() };
}

export async function restoreKeepAwake(): Promise<KeepAwakeResult | null> {
  if (!loadKeepAwakePreference()) return null;
  return setKeepAwakeEnabled(true);
}

export async function releaseKeepAwake(): Promise<void> {
  await applyAssertion(false);
}

export function resetKeepAwakeForTests(): void {
  _filePath = "";
  _child = null;
  _displayBlockerId = null;
  _appBlockerId = null;
  _runtime = {
    spawn: (cmd, args, opts) => spawn(cmd, args, opts ?? { stdio: "ignore" }),
    platform: () => process.platform,
  };
}
