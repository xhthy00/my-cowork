import { ChildProcess, spawn, spawnSync } from "child_process";
import { existsSync } from "fs";
import { get } from "http";
import * as path from "path";

// ── types ────────────────────────────────────────────────────────────────────

export interface BackendInfo {
  port: number;
  url: string;
  process: ChildProcess;
}

export interface RunnerOptions {
  cwd: string;
  dev?: boolean;
  healthTimeoutMs?: number;
  env?: Record<string, string>;
}

// ── constants ───────────────────────────────────────────────────────────────

const PORT_REGEX = /127\.0\.0\.1:(\d+)/;
const HEALTH_POLL_MS = 100;
const DEFAULT_HEALTH_TIMEOUT_MS = 15_000;

// ── runner ───────────────────────────────────────────────────────────────────

function resolvePackagedBackend(): { cmd: string; args: string[]; cwd: string } {
  // One-dir build (preferred): resources/python_runtime/python.exe.
  // Skips per-launch temp extraction of one-file; cold start ~1-3s vs 10-30s.
  const onedirExe = path.join(process.resourcesPath, "python_runtime", "python.exe");
  if (process.platform === "win32" && existsSync(onedirExe)) {
    return {
      cmd: onedirExe,
      args: ["--port", "0"],
      cwd: path.dirname(onedirExe),
    };
  }
  const cmd = path.join(
    process.resourcesPath,
    process.platform === "win32" ? "python_bin.exe" : "python_bin",
  );
  return {
    cmd,
    args: ["--port", "0"],
    // Packaged extraResources live next to the exe. Do not use repo
    // `backend/` — that path is inside app.asar and spawn() ENOENTs on Windows.
    cwd: path.dirname(cmd),
  };
}

function spawnCwd(preferred: string | undefined, fallback: string): string {
  if (preferred && existsSync(preferred)) return preferred;
  if (existsSync(fallback)) return fallback;
  return process.cwd();
}

export function start(options: RunnerOptions): Promise<BackendInfo> {
  const env = { ...process.env, ...options.env };
  env.PYTHONUTF8 = env.PYTHONUTF8 || "1";
  env.PYTHONIOENCODING = env.PYTHONIOENCODING || "utf-8";
  env.PYTHONUNBUFFERED = env.PYTHONUNBUFFERED || "1";
  const appModule = env.MY_COWORK_UVICORN_APP || "app.main:app";
  const packaged = options.dev ? null : resolvePackagedBackend();
  const cmd = options.dev ? "uv" : packaged!.cmd;
  const args = options.dev
    ? ["run", "uvicorn", appModule, "--port", "0"]
    : packaged!.args;

  if (packaged && !existsSync(packaged.cmd)) {
    return Promise.reject(new Error(`Packaged backend not found: ${packaged.cmd}`));
  }

  const proc = spawn(cmd, args, {
    cwd: packaged ? spawnCwd(packaged.cwd, process.cwd()) : options.cwd,
    env,
    windowsHide: true,
  });

  return new Promise<BackendInfo>((resolve, reject) => {
    let resolved = false;
    let stderrBuf = "";

    const onData = (chunk: Buffer) => {
      const text = chunk.toString();
      const m = text.match(PORT_REGEX);
      if (m && !resolved) {
        resolved = true;
        const port = parseInt(m[1], 10);
        waitForHealth(
          port,
          proc,
          options.healthTimeoutMs || DEFAULT_HEALTH_TIMEOUT_MS,
          resolve,
          reject,
        );
      }
    };

    proc.stdout.on("data", onData);
    proc.stderr.on("data", (chunk: Buffer) => {
      stderrBuf += chunk.toString();
      onData(chunk);
    });

    proc.on("error", (err) => {
      if (!resolved) reject(err);
    });

    proc.on("exit", (code) => {
      if (!resolved) {
        const detail = stderrBuf.trim();
        const suffix = detail ? `\n${detail.slice(-2000)}` : "";
        reject(new Error(`Python process exited with code ${code}${suffix}`));
      }
    });
  });
}

/** Stop uv/python backend including child uvicorn (plain kill leaves orphans). */
export function stop(proc: ChildProcess | null | undefined): void {
  if (!proc?.pid) return;
  const pid = proc.pid;
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(pid), "/T", "/F"], {
        stdio: "ignore",
      });
    } else {
      spawnSync("pkill", ["-TERM", "-P", String(pid)], { stdio: "ignore" });
      try {
        process.kill(pid, "SIGTERM");
      } catch {
        /* already dead */
      }
    }
  } catch {
    try {
      proc.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  }
}

// ── health polling ───────────────────────────────────────────────────────────

function waitForHealth(
  port: number,
  proc: ChildProcess,
  timeoutMs: number,
  resolve: (info: BackendInfo) => void,
  reject: (err: Error) => void,
) {
  const url = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + timeoutMs;

  function poll() {
    if (Date.now() > deadline) {
      return reject(
        new Error(`Backend health check timed out after ${timeoutMs} ms`),
      );
    }

    const req = get(`${url}/health`, (res) => {
      if (res.statusCode === 200) {
        resolve({ port, url, process: proc });
        return;
      }
      setTimeout(poll, HEALTH_POLL_MS);
    });

    req.on("error", () => {
      setTimeout(poll, HEALTH_POLL_MS);
    });
  }

  poll();
}
