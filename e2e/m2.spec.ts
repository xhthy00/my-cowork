/**
 * M2 smoke (Playwright + Electron via CDP).
 *
 * Playwright's ``_electron.launch`` hangs on Electron 35 (upstream:
 * --remote-debugging-port CLI rejection / handshake). We spawn Electron
 * ourselves with ``app.commandLine.appendSwitch('remote-debugging-port')``
 * and attach with ``chromium.connectOverCDP``.
 *
 * Fake LLM: ``app.e2e_app:app`` scripts Supervisor → FileWorker → fs_write.
 */
import { expect, test, chromium, type Browser, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "child_process";
import * as fs from "fs";
import * as http from "http";
import * as net from "net";
import * as os from "os";
import * as path from "path";

async function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        server.close();
        reject(new Error("failed to allocate port"));
        return;
      }
      const port = addr.port;
      server.close(() => resolve(port));
    });
  });
}

async function waitForCdp(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await new Promise<void>((resolve, reject) => {
        const req = http.get(`http://127.0.0.1:${port}/json/version`, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else reject(new Error(`status ${res.statusCode}`));
        });
        req.on("error", reject);
        req.setTimeout(500, () => {
          req.destroy();
          reject(new Error("timeout"));
        });
      });
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw new Error(`CDP not ready on port ${port} after ${timeoutMs}ms`);
}

test("m2 smoke: input → confirm modal → Desktop/hello.txt", async () => {
  test.setTimeout(180_000);

  const home = fs.mkdtempSync(path.join(os.tmpdir(), "mycowork-e2e-"));
  const desktop = path.join(home, "Desktop");
  fs.mkdirSync(desktop);
  const helloPath = path.join(desktop, "hello.txt");
  const cdpPort = await getFreePort();

  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const electronPath = require("electron") as string;
  const mainJs = path.join(__dirname, "..", "dist-electron", "main.js");

  const env: NodeJS.ProcessEnv = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  env.HOME = home;
  env.MY_COWORK_E2E = "1";
  env.MY_COWORK_CDP_PORT = String(cdpPort);
  env.MY_COWORK_UVICORN_APP = "app.e2e_app:app";
  env.MY_COWORK_E2E_PATH = helloPath;
  env.MY_COWORK_E2E_CONTENT = "hi";

  let proc: ChildProcess | undefined;
  let browser: Browser | undefined;

  try {
    proc = spawn(electronPath, [`--remote-debugging-port=${cdpPort}`, mainJs], {
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    proc.stderr?.on("data", (chunk) => {
      process.stderr.write(`[electron] ${chunk}`);
    });
    proc.stdout?.on("data", (chunk) => {
      process.stdout.write(`[electron] ${chunk}`);
    });
    proc.on("exit", (code, signal) => {
      process.stderr.write(`[electron] exited code=${code} signal=${signal}\n`);
    });

    await waitForCdp(cdpPort, 60_000);

    browser = await chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`);
    const context = browser.contexts()[0] ?? (await browser.newContext());
    let page: Page | undefined = context.pages()[0];
    if (!page) {
      page = await context.waitForEvent("page", { timeout: 60_000 });
    }

    await page.waitForSelector("textarea", { timeout: 90_000 });

    // Backend starts after the window; poll IPC until the URL is ready.
    await expect
      .poll(
        async () =>
          page!.evaluate(async () => {
            // @ts-expect-error preload api
            return (await window.api?.getBackendUrl?.()) || "";
          }),
        { timeout: 90_000 },
      )
      .toMatch(/127\.0\.0\.1/);

    await page.fill("textarea", "在桌面写 hello.txt 内容 hi");
    await page.click('button[title="发送"]');

    await page.getByRole("button", { name: "允许" }).waitFor({ timeout: 60_000 });
    await page.getByRole("button", { name: "允许" }).click();

    await expect.poll(() => fs.existsSync(helloPath), { timeout: 30_000 }).toBe(true);
    expect(fs.readFileSync(helloPath, "utf8")).toBe("hi");
  } finally {
    await browser?.close().catch(() => undefined);
    if (proc && !proc.killed) {
      proc.kill("SIGTERM");
    }
  }
});
