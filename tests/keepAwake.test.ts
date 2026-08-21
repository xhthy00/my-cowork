import { EventEmitter } from "events";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  configureKeepAwakeRuntime,
  getKeepAwakeState,
  initKeepAwake,
  keepAwakeSpawnSpec,
  loadKeepAwakePreference,
  releaseKeepAwake,
  resetKeepAwakeForTests,
  restoreKeepAwake,
  setKeepAwakeEnabled,
} from "../electron/keepAwake";

class MockChild extends EventEmitter {
  killed = false;
  kill = vi.fn((_signal?: NodeJS.Signals | number) => {
    this.killed = true;
    queueMicrotask(() => this.emit("exit", 0, null));
    return true;
  });
}

function spawnOk() {
  const child = new MockChild();
  queueMicrotask(() => child.emit("spawn"));
  return child;
}

function spawnFail(message = "spawn ENOENT") {
  const child = new MockChild();
  queueMicrotask(() => child.emit("error", new Error(message)));
  return child;
}

describe("keepAwakeSpawnSpec", () => {
  it("returns caffeinate -dis on darwin", () => {
    expect(keepAwakeSpawnSpec("darwin")).toEqual({
      cmd: "caffeinate",
      args: ["-dis"],
    });
  });

  it("returns systemd-inhibit on linux", () => {
    expect(keepAwakeSpawnSpec("linux")).toEqual({
      cmd: "systemd-inhibit",
      args: [
        "--what=sleep",
        "--why=MyCowork keep-awake is enabled",
        "--mode=block",
        "sleep",
        "infinity",
      ],
    });
  });

  it("returns null on win32 (powerSaveBlocker)", () => {
    expect(keepAwakeSpawnSpec("win32")).toBeNull();
  });
});

describe("keepAwake", () => {
  let tmp: string;
  const spawnMock = vi.fn();

  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-keep-awake-"));
    resetKeepAwakeForTests();
    spawnMock.mockReset();
    initKeepAwake(tmp);
  });

  afterEach(async () => {
    await releaseKeepAwake();
    resetKeepAwakeForTests();
    fs.rmSync(tmp, { recursive: true, force: true });
  });

  it("spawns caffeinate on darwin and kills the child when disabled", async () => {
    const child = spawnOk();
    spawnMock.mockReturnValue(child);
    configureKeepAwakeRuntime({
      platform: () => "darwin",
      spawn: spawnMock,
    });

    const on = await setKeepAwakeEnabled(true);
    expect(on).toEqual({ ok: true, enabled: true });
    expect(spawnMock).toHaveBeenCalledWith("caffeinate", ["-dis"], {
      stdio: "ignore",
    });
    expect(loadKeepAwakePreference()).toBe(true);

    const again = await setKeepAwakeEnabled(true);
    expect(again).toEqual({ ok: true, enabled: true });
    expect(spawnMock).toHaveBeenCalledTimes(1);

    const off = await setKeepAwakeEnabled(false);
    expect(off).toEqual({ ok: true, enabled: false });
    expect(child.kill).toHaveBeenCalled();
    expect(loadKeepAwakePreference()).toBe(false);
  });

  it("spawns systemd-inhibit on linux", async () => {
    spawnMock.mockReturnValue(spawnOk());
    configureKeepAwakeRuntime({
      platform: () => "linux",
      spawn: spawnMock,
    });

    const on = await setKeepAwakeEnabled(true);
    expect(on.ok).toBe(true);
    expect(spawnMock).toHaveBeenCalledWith(
      "systemd-inhibit",
      [
        "--what=sleep",
        "--why=MyCowork keep-awake is enabled",
        "--mode=block",
        "sleep",
        "infinity",
      ],
      { stdio: "ignore" },
    );
  });

  it("uses powerSaveBlocker on win32", async () => {
    const start = vi.fn((type: string) => (type === "prevent-display-sleep" ? 11 : 22));
    const stop = vi.fn(() => true);
    configureKeepAwakeRuntime({
      platform: () => "win32",
      spawn: spawnMock,
      powerSaveBlocker: { start, stop },
    });

    const on = await setKeepAwakeEnabled(true);
    expect(on).toEqual({ ok: true, enabled: true });
    expect(start).toHaveBeenCalledWith("prevent-display-sleep");
    expect(start).toHaveBeenCalledWith("prevent-app-suspension");
    expect(spawnMock).not.toHaveBeenCalled();
    expect(loadKeepAwakePreference()).toBe(true);

    const off = await setKeepAwakeEnabled(false);
    expect(off.enabled).toBe(false);
    expect(stop).toHaveBeenCalledWith(11);
    expect(stop).toHaveBeenCalledWith(22);
  });

  it("does not persist when spawn fails", async () => {
    spawnMock.mockReturnValue(spawnFail());
    configureKeepAwakeRuntime({
      platform: () => "darwin",
      spawn: spawnMock,
    });

    const result = await setKeepAwakeEnabled(true);
    expect(result.ok).toBe(false);
    expect(result.enabled).toBe(false);
    expect(result.error).toMatch(/ENOENT/);
    expect(fs.existsSync(path.join(tmp, "keep-awake.json"))).toBe(false);
    expect(getKeepAwakeState()).toEqual({ enabled: false, supported: true });
  });

  it("restores from preference on startup", async () => {
    fs.writeFileSync(
      path.join(tmp, "keep-awake.json"),
      JSON.stringify({ enabled: true }, null, 2),
    );
    spawnMock.mockReturnValue(spawnOk());
    configureKeepAwakeRuntime({
      platform: () => "darwin",
      spawn: spawnMock,
    });

    const restored = await restoreKeepAwake();
    expect(restored).toEqual({ ok: true, enabled: true });
    expect(spawnMock).toHaveBeenCalledWith("caffeinate", ["-dis"], {
      stdio: "ignore",
    });
  });

  it("restore is a no-op when preference is off", async () => {
    configureKeepAwakeRuntime({
      platform: () => "darwin",
      spawn: spawnMock,
    });
    expect(await restoreKeepAwake()).toBeNull();
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it("rolls back the assertion when persist fails", async () => {
    const fileAsDir = path.join(tmp, "not-a-dir");
    fs.writeFileSync(fileAsDir, "x");
    initKeepAwake(fileAsDir);

    const child = spawnOk();
    spawnMock.mockReturnValue(child);
    configureKeepAwakeRuntime({
      platform: () => "darwin",
      spawn: spawnMock,
    });

    const result = await setKeepAwakeEnabled(true);
    expect(result.ok).toBe(false);
    expect(child.kill).toHaveBeenCalled();
    expect(getKeepAwakeState().enabled).toBe(false);
  });
});
