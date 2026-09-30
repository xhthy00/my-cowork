import { readFile } from "fs/promises";
import * as path from "path";
import * as os from "os";

type RunningRegistry = { generation?: string; apps?: Record<string, { version?: string; dev_revision?: string; enabled?: boolean }> };
let runningRegistry: RunningRegistry = {};
export function publishAppRuntime(runtime: { generation: string; apps: Array<{ id: string; version?: string; dev_revision?: string; status: string }> } | null): void {
  runningRegistry = runtime ? { generation: runtime.generation, apps: Object.fromEntries(runtime.apps.filter(app => app.status === "ready").map(app => [app.id, { version: app.version, dev_revision: app.dev_revision, enabled: true }])) } : {};
}

const APP_ID = /^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$/;
const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
};

export function industryAppsRoot(): string {
  if (process.env.MY_COWORK_INDUSTRY_APPS_ROOT) {
    return path.resolve(process.env.MY_COWORK_INDUSTRY_APPS_ROOT);
  }
  const root = process.env.MY_COWORK_DATA_DIR || path.join(os.homedir(), ".my-cowork");
  return path.join(path.resolve(root), "industry-apps");
}

export function resolveAppAsset(
  url: string,
  registry: RunningRegistry,
  root: string,
): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "mycowork-app:" || !APP_ID.test(parsed.hostname)) return null;
  const entry = registry.apps?.[parsed.hostname];
  if (!entry?.enabled || !entry.version || !/^\d+\.\d+\.\d+$/.test(entry.version)) return null;
  let pathname: string;
  try {
    pathname = decodeURIComponent(parsed.pathname);
  } catch {
    return null;
  }
  if (pathname.includes("\\") || pathname.includes("\0") || pathname.split("/").includes("..")) return null;
  if (registry.generation) {
    const prefix = "/" + registry.generation + "/";
    if (!pathname.startsWith(prefix)) return null;
    pathname = pathname.slice(prefix.length - 1);
  }
  if (entry.dev_revision && (process.env.MY_COWORK_APP_DEV !== "1" || process.env.MY_COWORK_DEV_APP_ID !== parsed.hostname || !/^[0-9a-f]{64}$/.test(entry.dev_revision))) return null;
  const base = entry.dev_revision
    ? path.resolve(root, "development", parsed.hostname, entry.dev_revision, "frontend", "dist")
    : path.resolve(root, "packages", parsed.hostname, entry.version, "frontend", "dist");
  const asset = path.resolve(base, "." + (pathname === "/" ? "/index.html" : pathname));
  if (!asset.startsWith(base + path.sep)) return null;
  return asset;
}

export async function serveAppAsset(url: string, root = industryAppsRoot(), registry = runningRegistry): Promise<Response> {
  const asset = resolveAppAsset(url, registry, root);
  if (!asset) return new Response("Forbidden", { status: 403 });
  try {
    const bytes = await readFile(asset);
    return new Response(bytes, {
      status: 200,
      headers: {
        "Content-Type": MIME[path.extname(asset).toLowerCase()] || "application/octet-stream",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "Content-Security-Policy": [
          "default-src 'none'",
          "script-src 'self'",
          "style-src 'self'",
          "img-src 'self' data:",
          "font-src 'self'",
          "connect-src 'none'",
          "base-uri 'none'",
          "form-action 'none'",
        ].join("; "),
      },
    });
  } catch {
    return new Response("Not Found", { status: 404 });
  }
}

export function validAppRequest(appId: string, method: string, requestPath: string): boolean {
  if (!APP_ID.test(appId)) return false;
  if (!["GET", "POST", "PATCH", "PUT", "DELETE"].includes(method)) return false;
  if (!requestPath.startsWith("/") || requestPath.startsWith("//") || requestPath.includes("\\") || requestPath.includes("#")) return false;
  try {
    const rawPath = decodeURIComponent(requestPath.split("?")[0]);
    if (rawPath.split("/").some((part) => part === "." || part === "..")) return false;
    const parsed = new URL(requestPath, "http://local.invalid");
    return parsed.origin === "http://local.invalid" && !requestPath.toLowerCase().includes("%2f");
  } catch {
    return false;
  }
}
