#!/usr/bin/env node
/**
 * One-command local dev: Vite renderer + Electron (after :5174 is up).
 * Ctrl+C stops both and cleans leftover my-cowork uvicorn processes.
 */
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..");
const BACKEND_DIR = path.join(REPO_ROOT, "backend");
const children = [];
let shuttingDown = false;

function run(command, args, label) {
  const child = spawn(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: process.env,
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

/** Kill orphaned my-cowork uvicorn left behind by uv/Electron. */
function cleanupUvicorn() {
  try {
    if (process.platform === "win32") {
      const marker = BACKEND_DIR.replace(/'/g, "''");
      spawnSync(
        "powershell",
        [
          "-NoProfile",
          "-Command",
          `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*${marker}*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`,
        ],
        { stdio: "ignore" },
      );
    } else {
      spawnSync("pkill", ["-f", `${BACKEND_DIR}.*uvicorn`], {
        stdio: "ignore",
      });
    }
  } catch {
    // best-effort
  }
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
  cleanupUvicorn();
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
  run("npx", ["vite"], "renderer");
  await waitForUrl("http://127.0.0.1:5174/");

  const compiled = spawnSync("npx", ["tsc"], {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: process.env,
  });
  if (compiled.status !== 0) {
    shutdown(compiled.status || 1);
    return;
  }

  run("npx", ["electron", "dist-electron/main.js"], "electron");
}

main().catch((err) => {
  console.error(err.message || err);
  shutdown(1);
});
