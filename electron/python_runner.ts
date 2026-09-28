import { ChildProcess, spawn, spawnSync } from "child_process";
import { existsSync } from "fs";
import { get, type ClientRequest } from "http";
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
  signal?: AbortSignal;
}

// ── constants ───────────────────────────────────────────────────────────────

const PORT_REGEX = /127\.0\.0\.1:(\d+)/;
const HEALTH_POLL_MS = 100;
const DEFAULT_HEALTH_TIMEOUT_MS = 90_000;

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
  const cancelled = () => Object.assign(new Error("Backend startup cancelled"), { name: "AbortError" });
  if (options.signal?.aborted) return Promise.reject(cancelled());
  const env = { ...process.env, ...options.env };
  env.PYTHONUTF8 = env.PYTHONUTF8 || "1";
  env.PYTHONIOENCODING = env.PYTHONIOENCODING || "utf-8";
  env.PYTHONUNBUFFERED = env.PYTHONUNBUFFERED || "1";
  if (!options.dev) {
    injectPackagedSkillEnv(env);
    injectPackagedBrowserEnv(env);
  }
  const appModule = env.MY_COWORK_UVICORN_APP || "app.main:app";
  const packaged = options.dev ? null : resolvePackagedBackend();
  const cmd = options.dev ? "uv" : packaged!.cmd;
  const args = options.dev
    ? ["run", "--no-sync", "uvicorn", appModule, "--port", "0", "--reload", "--reload-dir", path.join(options.cwd, "app")]
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

  const startedAt = Date.now();
  console.info("[backend] starting Python");
  return new Promise<BackendInfo>((resolve, reject) => {
    let settled = false;
    let port: number | undefined;
    let stderrBuf = "";
    let stage = "waiting for Python to announce a port";
    let request: ClientRequest | undefined;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    const timeoutMs = options.healthTimeoutMs ?? DEFAULT_HEALTH_TIMEOUT_MS;
    const deadline = setTimeout(() => finish(new Error(
      `Backend startup timed out after ${timeoutMs} ms (${stage})`,
    )), timeoutMs);

    function finish(error?: Error) {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      clearTimeout(pollTimer);
      options.signal?.removeEventListener("abort", onAbort);
      request?.destroy();
      if (error) {
        stop(proc);
        reject(error);
      } else {
        console.info(`[backend] ready after ${Date.now() - startedAt} ms`);
        resolve({ port: port!, url: `http://127.0.0.1:${port}`, process: proc });
      }
    }

    function onAbort() { finish(cancelled()); }
    options.signal?.addEventListener("abort", onAbort, { once: true });

    function poll() {
      if (settled) return;
      let responded = false;
      const retry = () => {
        if (!settled) pollTimer = setTimeout(poll, HEALTH_POLL_MS);
      };
      const pending = get(`http://127.0.0.1:${port}/health`, (res) => {
        responded = true;
        res.resume();
        if (settled) return;
        if (res.statusCode === 200) finish();
        else retry();
      });
      request = pending;
      pending.once("error", () => { if (!responded) retry(); });
      pending.setTimeout(1000, () => pending.destroy(new Error("Health request timed out")));
    }

    // A port may span chunks; only parse complete log lines.
    const tails = { stdout: "", stderr: "" };
    const onData = (chunk: Buffer, stream: keyof typeof tails) => {
      if (settled) return;
      const lines = (tails[stream] + chunk.toString()).split(/\r?\n/);
      tails[stream] = lines.pop()!.slice(-4000);
      for (const line of lines) {
        if (line.startsWith("[startup]")) {
          stage = line;
          console.info(line);
        }
        const match = line.match(PORT_REGEX);
        if (match && port === undefined) {
          port = Number(match[1]);
          stage = "waiting for application initialization and health";
          console.info(`[backend] port announced after ${Date.now() - startedAt} ms`);
          poll();
        }
      }
    };
    proc.stdout.on("data", (chunk: Buffer) => onData(chunk, "stdout"));
    proc.stderr.on("data", (chunk: Buffer) => {
      if (!settled) stderrBuf = (stderrBuf + chunk.toString()).slice(-4000);
      onData(chunk, "stderr");
    });
    proc.on("error", (err) => finish(err));
    proc.on("exit", (code) => {
      const detail = stderrBuf.trim();
      finish(new Error(`Python process exited with code ${code}${detail ? `\n${detail.slice(-2000)}` : ""}`));
    });
    if (options.signal?.aborted) onAbort();
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
