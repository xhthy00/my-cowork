#!/usr/bin/env node
/**
 * One-command local dev: Vite renderer + Electron.
 * Optional .env.development.local configures an isolated checkout.
 */
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");
const net = require("net");
const { parseEnv } = require("node:util");

const REPO_ROOT = path.resolve(__dirname, "..");
const localEnvPath = path.join(REPO_ROOT, ".env.development.local");
if (fs.existsSync(localEnvPath) && process.env.MY_COWORK_DEV_CONTROL !== "1") {
  Object.assign(process.env, parseEnv(fs.readFileSync(localEnvPath, "utf8")));
}
const rendererPort = Number(process.env.VITE_DEV_SERVER_PORT || 5174);
const rendererUrl = `http://127.0.0.1:${rendererPort}/`;
process.env.VITE_DEV_SERVER_URL = rendererUrl;
const children = [];
let shuttingDown = false;

function run(command, args, label) {
  const child = spawn(command, args, {
    stdio: "inherit",
    cwd: REPO_ROOT,
    windowsHide: true,
    env: process.env,
  });
  child.on("error", (error) => {
    console.error(`[${label}] ${error.message}`);
    shutdown(1);
  });
  child.on("exit", (code, signal) => {
    if (shuttingDown || signal) return;
    if (code && code !== 0) {
      console.error(`[${label}] exited with code ${code}`);
    }
    shutdown(code || 0);
  });
  children.push(child);
  return child;
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.pid || child.exitCode !== null) continue;
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore", windowsHide: true,
      });
    } else if (!child.killed) {
      child.kill("SIGTERM");
    }
  }
  process.exit(code);
}

function waitForUrl(url, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (Date.now() > deadline) {
        reject(new Error(`Timed out waiting for ${url}`));
        return;
      }
      const req = http.get(url, { family: 4 }, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => setTimeout(tick, 250));
      req.setTimeout(2000, () => {
        req.destroy();
        setTimeout(tick, 250);
      });
    };
    tick();
  });
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

async function main() {
  if (!Number.isInteger(rendererPort) || rendererPort < 1 || rendererPort > 65535) {
    throw new Error("VITE_DEV_SERVER_PORT must be an integer between 1 and 65535");
  }
  // Refuse an occupied port before probing; never attach to another checkout.
  await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once("error", reject);
    probe.listen(rendererPort, "127.0.0.1", () => probe.close(resolve));
  });
  const viteCli = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
  run(process.execPath, [viteCli, "--port", String(rendererPort)], "renderer");
  await waitForUrl(rendererUrl);

  const compiled = spawnSync(process.execPath, [require.resolve("typescript/bin/tsc")], {
    stdio: "inherit",
    cwd: REPO_ROOT,
    windowsHide: true,
    env: process.env,
  });
  if (compiled.status !== 0) {
    shutdown(compiled.status || 1);
    return;
  }

  run(require("electron"), ["dist-electron/main.js"], "electron");
}

main().catch((err) => {
  console.error(err.message || err);
  shutdown(1);
});
