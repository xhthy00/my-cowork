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

export function resolvePackagedBackend(): { cmd: string; args: string[]; cwd: string } {
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

function injectPackagedSkillEnv(env: Record<string, string | undefined>): void {
  // extraResources: resources/example-skills → {resourcesPath}/resources/example-skills
  const exampleSkills = path.join(
    process.resourcesPath,
    "resources",
    "example-skills",
  );
  if (existsSync(exampleSkills) && !env.MY_COWORK_EXAMPLE_SKILLS) {
    env.MY_COWORK_EXAMPLE_SKILLS = exampleSkills;
  }
}

function injectPackagedBrowserEnv(env: Record<string, string | undefined>): void {
  const browsers = path.join(process.resourcesPath, "playwright-browsers");
  if (existsSync(browsers) && !env.PLAYWRIGHT_BROWSERS_PATH) {
    env.PLAYWRIGHT_BROWSERS_PATH = browsers;
  }
}

export function start(options: RunnerOptions): Promise<BackendInfo> {
  const env = { ...process.env, ...options.env };
  env.PYTHONUTF8 = env.PYTHONUTF8 || "1";
  env.PYTHONIOENCODING = env.PYTHONIOENCODING || "utf-8";
  env.PYTHONUNBUFFERED = env.PYTHONUNBUFFERED || "1";
  if (!options.dev) {
    injectPackagedSkillEnv(env);
    injectPackagedBrowserEnv(env);
  }
  env.MY_COWORK_PARENT_PIPE = "1";
  const packaged = options.dev ? null : resolvePackagedBackend();
  const cmd = options.dev ? path.join(options.cwd, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python") : packaged!.cmd;
  // A single owned process must hold the run lock. A reloader would start a
  // replacement behind the lifecycle coordinator while data is being restored.
  const args = options.dev
    ? (env.MY_COWORK_UVICORN_APP
      ? ["-m", "uvicorn", env.MY_COWORK_UVICORN_APP, "--port", "0"]
      : ["-m", "app.main", "--port", "0"])
    : packaged!.args;

  if (packaged && !existsSync(packaged.cmd)) {
    return Promise.reject(new Error(`Packaged backend not found: ${packaged.cmd}`));
  }

  const proc = spawn(cmd, args, {
    cwd: packaged ? spawnCwd(packaged.cwd, process.cwd()) : options.cwd,
    env,
    windowsHide: true,
    // Keep uvicorn's reloader and worker in one stoppable process group.
    detached: Boolean(options.dev && process.platform !== "win32"),
  });
  (proc as ChildProcess & { backendProcessGroup?: boolean }).backendProcessGroup =
    Boolean(options.dev && process.platform !== "win32");

  return new Promise<BackendInfo>((resolve, reject) => {
    let resolved = false;
    let stderrBuf = "";
    let settled = false;
    const succeed = (info: BackendInfo) => {
      if (settled) return;
      settled = true;
      clearTimeout(startTimer);
      resolve(info);
    };
    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(startTimer);
      void stopAndWait(proc).then(() => reject(err), (stopError) => reject(new Error(`${err.message}; ${stopError}`)));
    };
    const startTimer = setTimeout(() => fail(new Error("Backend startup timed out")), options.healthTimeoutMs || DEFAULT_HEALTH_TIMEOUT_MS);

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
          succeed,
          fail,
        );
      }
    };

    proc.stdout.on("data", onData);
    proc.stderr.on("data", (chunk: Buffer) => {
      stderrBuf = (stderrBuf + chunk.toString()).slice(-4000);
      onData(chunk);
    });

    proc.on("error", (err) => {
      fail(err);
    });

    proc.on("exit", (code) => {
      if (!settled) {
        const detail = stderrBuf.trim();
        const suffix = detail ? `\n${detail.slice(-2000)}` : "";
        fail(new Error(`Python process exited with code ${code}${suffix}`));
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
        stdio: "ignore", windowsHide: true,
      });
    } else if ((proc as ChildProcess & { backendProcessGroup?: boolean }).backendProcessGroup) {
      process.kill(-pid, "SIGTERM");
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

export async function stopAndWait(proc: ChildProcess | null | undefined): Promise<void> {
  if (!proc || proc.exitCode != null || proc.signalCode != null) return;
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("无法确认后端已经退出，已停止更新")), 10_000);
    proc.once("exit", () => { clearTimeout(timeout); resolve(); });
    proc.stdin?.end();
    stop(proc);
  });
}

export function startMaintenance(options: RunnerOptions): ChildProcess {
  const packaged = options.dev ? null : resolvePackagedBackend();
  const cmd = options.dev
    ? path.join(options.cwd, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python")
    : packaged!.cmd;
  return spawn(cmd, options.dev ? ["-m", "app.main", "--industry-maintenance"] : ["--industry-maintenance"], {
    cwd: packaged?.cwd || options.cwd,
    env: { ...process.env, ...options.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    windowsHide: true,
  });
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
