import { readFile } from "fs/promises";
import * as path from "path";
import * as os from "os";

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
  registry: { apps?: Record<string, { version?: string; enabled?: boolean }> },
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
  const base = path.join(root, "packages", parsed.hostname, entry.version, "frontend", "dist");
  const asset = path.resolve(base, "." + (pathname === "/" ? "/index.html" : pathname));
  if (!asset.startsWith(base + path.sep)) return null;
  return asset;
}

export async function serveAppAsset(url: string, root = industryAppsRoot()): Promise<Response> {
  let registry: { apps?: Record<string, { version?: string; enabled?: boolean }> };
  try {
    registry = JSON.parse(await readFile(path.join(root, "registry.json"), "utf-8"));
  } catch {
    return new Response("Application registry unavailable", { status: 404 });
  }
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
