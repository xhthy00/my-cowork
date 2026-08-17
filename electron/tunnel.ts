/**
 * Spawn cloudflared quick tunnel and resolve the public HTTPS URL.
 */
import { spawn, type ChildProcess } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";

export type SpawnFn = (
  command: string,
  args: readonly string[],
) => ChildProcess;

const TUNNEL_URL_RE = /https:\/\/[a-zA-Z0-9-]+\.trycloudflare\.com/;
const BIN_NAME = process.platform === "win32" ? "cloudflared.exe" : "cloudflared";

export interface TunnelHandle {
  url: string;
  stop: () => void;
}

export function cloudflaredMissingMessage(): string {
  if (process.platform === "darwin") {
    return "未找到 cloudflared。请先安装：brew install cloudflared";
  }
  if (process.platform === "win32") {
    return "未找到 cloudflared。请安装后重试：https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/";
  }
  return "未找到 cloudflared。请先安装 cloudflared 后重试。";
}

/** Absolute path if installed in a known location; otherwise the bare binary name. */
export function resolveCloudflaredBin(): string {
  const fromEnv = process.env.MY_COWORK_CLOUDFLARED || process.env.CLOUDFLARED_PATH;
  if (fromEnv && fs.existsSync(fromEnv)) return fromEnv;

  const home = os.homedir();
  const candidates =
    process.platform === "win32"
      ? [
          path.join(process.env.PROGRAMFILES || "C:\\Program Files", "cloudflared", BIN_NAME),
          path.join(process.env.LOCALAPPDATA || "", "cloudflared", BIN_NAME),
        ]
      : [
          "/opt/homebrew/bin/cloudflared",
          "/usr/local/bin/cloudflared",
          "/usr/bin/cloudflared",
          path.join(home, ".local", "bin", "cloudflared"),
        ];
  return candidates.find((p) => Boolean(p) && fs.existsSync(p)) || BIN_NAME;
}

function defaultSpawn(cmd: string, args: readonly string[]): ChildProcess {
  return spawn(cmd, [...args], { stdio: ["ignore", "pipe", "pipe"] });
}

export function startTunnel(
  targetUrl: string,
  spawnFn: SpawnFn = defaultSpawn,
  timeoutMs = 30_000,
): Promise<TunnelHandle> {
  const child = spawnFn(resolveCloudflaredBin(), ["tunnel", "--url", targetUrl]);

  return new Promise((resolve, reject) => {
    let settled = false;
    const chunks: string[] = [];

    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.kill();
      reject(err);
    };

    const succeed = (url: string) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        url,
        stop: () => {
          child.kill();
        },
      });
    };

    const onData = (buf: Buffer) => {
      const text = buf.toString("utf8");
      chunks.push(text);
      const match = TUNNEL_URL_RE.exec(chunks.join(""));
      if (match) {
        succeed(match[0]);
      }
    };

    child.stdout?.on("data", onData);
    child.stderr?.on("data", onData);
    child.on("error", (err) => {
      const code = (err as NodeJS.ErrnoException).code;
      fail(code === "ENOENT" ? new Error(cloudflaredMissingMessage()) : err);
    });
    child.on("exit", (code) => {
      if (!settled) {
        fail(new Error(`cloudflared exited early (code=${code})`));
      }
    });

    const timer = setTimeout(() => {
      fail(new Error(`cloudflared tunnel URL not ready within ${timeoutMs}ms`));
    }, timeoutMs);
  });
}
