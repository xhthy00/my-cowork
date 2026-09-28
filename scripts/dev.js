#!/usr/bin/env node
/**
 * One-command local dev: Vite renderer + Electron (after :5174 is up).
 * Ctrl+C stops both and their owned subprocesses.
 */
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const path = require("path");
const children = [];
let shuttingDown = false;
const startedAt = Date.now();
const stage = (name) => console.log(`[dev] ${name} after ${Date.now() - startedAt} ms`);

function run(command, args, label) {
  const child = spawn(command, args, {
    stdio: ["ignore", "pipe", "pipe"],
    // Keep Ctrl+C in this supervisor. If shells die first, taskkill can no
    // longer find the uv/Python descendants through their original parents.
    detached: true,
    windowsHide: true,
    env: process.env,
  });
  child.stdout?.pipe(process.stdout, { end: false });
  child.stderr?.pipe(process.stderr, { end: false });
  child.on("error", (error) => {
    console.error(`[${label}] ${error.message}`);
    shutdown(1);
  });
  child.on("exit", (code, signal) => {
    if (shuttingDown) return;
    if (signal) {
      console.error(`[${label}] exited with signal ${signal}`);
      shutdown(1);
      return;
    }
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
    if (process.platform === "win32" && child.pid) {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
    } else if (child.pid) {
      try { process.kill(-child.pid, "SIGTERM"); } catch { /* already exited */ }
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
  const vite = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
  run(process.execPath, [vite], "renderer");
  await waitForUrl("http://127.0.0.1:5174/");
  stage("renderer ready");

  const compiled = spawnSync(process.execPath, [require.resolve("typescript/bin/tsc")], {
    stdio: "inherit",
    env: process.env,
  });
  if (compiled.status !== 0) {
    shutdown(compiled.status || 1);
    return;
  }
  stage("Electron compilation ready");
  run(require("electron"), ["dist-electron/main.js"], "electron");
}

main().catch((err) => {
  console.error(err.message || err);
  shutdown(1);
});
