import { EventEmitter } from "node:events";
import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import ts from "typescript";
import { expect, it, vi } from "vitest";

it.each(["win32", "darwin"])("starts the packaged backend without a model or API key on %s", async (platform) => {
  // Exercise the real main-process launcher, including its credential handling,
  // without launching Electron or copying the packaged Python environment.
  const source = readFileSync(new URL("../electron/main.ts", import.meta.url), "utf8");
  const block = source.slice(source.indexOf("async function startBackendOnce("), source.indexOf("function notifyBackendReady"));
  const child = new EventEmitter();
  const start = vi.fn().mockResolvedValue({ url: "http://127.0.0.1:54321", process: child });
  const context = {
    buildPythonEnv: vi.fn().mockResolvedValue({}),
    process: { env: {}, platform, resourcesPath: "/packaged/resources" },
    path, os: { homedir: () => "/home/user" }, fs: { existsSync: () => false },
    __dirname: "/packaged/app.asar/dist-electron",
    isDev: false, isE2E: false, pdfServer: null,
    getPackageVersion: () => "0.1.3", prepareTerminalPython: () => null,
    industryToken: "desktop-token", start,
    backendUrl: "", backendProc: null,
  };
  const launch = vm.runInNewContext(ts.transpile(block) + "\nstartBackendOnce;", context);

  await expect(launch()).resolves.toBe("http://127.0.0.1:54321");
  expect(start).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
    dev: false,
    cwd: "/packaged/resources",
    env: expect.objectContaining({ MY_COWORK_INDUSTRY_TOKEN: "desktop-token" }),
  }));
  expect(start.mock.calls[0][0].env.MY_COWORK_API_KEY).toBeUndefined();
  expect(context.backendProc).toBe(child);
  expect(context.backendUrl).toBe("http://127.0.0.1:54321");
});
