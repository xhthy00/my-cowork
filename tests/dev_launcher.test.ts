import { EventEmitter } from "events";
import { readFileSync } from "fs";
import { runInNewContext } from "vm";
import * as path from "path";
import { expect, it, vi } from "vitest";

it.each([
  ["win32", "interrupt"], ["linux", "interrupt"],
  ["win32", "child-signal"], ["linux", "child-signal"],
])("stops only its owned process trees on %s after %s", async (platform, trigger) => {
  const children: Array<EventEmitter & { pid: number; kill: ReturnType<typeof vi.fn> }> = [];
  const spawn = vi.fn(() => {
    const child = Object.assign(new EventEmitter(), { pid: 123450 + children.length, kill: vi.fn() });
    children.push(child);
    return child;
  });
  const spawnSync = vi.fn(() => ({ status: 0 }));
  const process = Object.assign(new EventEmitter(), { platform, execPath: "node.exe", env: {}, exit: vi.fn(), kill: vi.fn() });
  runInNewContext(readFileSync("scripts/dev.js", "utf8"), {
    process, console: { log: vi.fn(), error: vi.fn() }, setTimeout,
    require: Object.assign((name: string) => {
      if (name === "path") return path;
      if (name === "electron") return "electron.exe";
      if (name === "child_process") return { spawn, spawnSync };
      if (name === "http") return { get: (_url: string, _options: unknown, cb: (res: unknown) => void) => {
        queueMicrotask(() => cb({ resume: vi.fn() }));
        return Object.assign(new EventEmitter(), { setTimeout: vi.fn() });
      } };
      throw new Error(`Unexpected dependency: ${name}`);
    }, { resolve: (name: string) => name }),
  });
  await vi.waitFor(() => expect(children).toHaveLength(2));
  expect(spawn).toHaveBeenCalledWith("electron.exe", ["dist-electron/main.js"],
    expect.objectContaining({ detached: true, windowsHide: true }));
  if (trigger === "interrupt") process.emit("SIGINT");
  else children[1].emit("exit", null, "SIGKILL");
  const kills = spawnSync.mock.calls.filter((call) => call[0] === "taskkill");
  if (platform === "win32") {
    expect(kills.map((call) => call[1])).toEqual([
      ["/pid", "123450", "/T", "/F"], ["/pid", "123451", "/T", "/F"],
    ]);
    expect(process.kill).not.toHaveBeenCalled();
  } else {
    expect(kills).toHaveLength(0);
    expect(process.kill.mock.calls).toEqual([[-123450, "SIGTERM"], [-123451, "SIGTERM"]]);
  }
  expect(children.every((child) => child.kill.mock.calls.length === 0)).toBe(true);
  expect(process.exit).toHaveBeenCalledWith(trigger === "interrupt" ? 0 : 1);
});
