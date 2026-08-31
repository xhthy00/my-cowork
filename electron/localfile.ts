/**
 * localfile:// URL parsing and allow-list for the preview <webview>.
 *
 * Chromium (standard custom scheme) rewrites localfile:///C:/Users/x into
 * localfile://c/Users/x (hostname = drive letter). Reconstruct a real
 * filesystem path and compare roots in a case-insensitive way on Windows.
 */
import * as path from "path";

type Platform = NodeJS.Platform;

function pathFor(platform: Platform): path.PlatformPath {
  return platform === "win32" ? path.win32 : path.posix;
}

function decodePathname(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/** Convert a localfile:// request URL into an absolute filesystem path. */
export function localfileUrlToFsPath(
  requestUrl: string,
  platform: Platform = process.platform,
): string {
  const p = pathFor(platform);
  try {
    const u = new URL(requestUrl);
    const host = (u.hostname || "").replace(/:$/, "");
    const pathname = decodePathname(u.pathname || "");

    if (platform === "win32") {
      // localfile://c/Users/... or localfile://c:/Users/...
      if (/^[a-zA-Z]$/.test(host)) {
        const rest = pathname.replace(/^\/+/, "").replace(/\//g, "\\");
        return p.resolve(`${host.toUpperCase()}:\\${rest}`);
      }
      // localfile:///C:/Users/... (empty host, pathname /C:/Users/...)
      const drivePath = pathname.match(/^\/([a-zA-Z]):(?:\/(.*))?$/);
      if (drivePath) {
        const rest = (drivePath[2] || "").replace(/\//g, "\\");
        return p.resolve(`${drivePath[1].toUpperCase()}:\\${rest}`);
      }
      // localfile:///c/Users/... (empty host, pathname /c/Users/...)
      const bareDrive = pathname.match(/^\/([a-zA-Z])\/(.*)$/);
      if (bareDrive) {
        const rest = bareDrive[2].replace(/\//g, "\\");
        return p.resolve(`${bareDrive[1].toUpperCase()}:\\${rest}`);
      }
    }

    if (host) {
      let abs = path.posix.normalize(`/${host}${pathname}`);
      if (platform === "darwin" && /^\/users\//i.test(abs)) {
        abs = "/Users" + abs.slice("/users".length);
      }
      return p.resolve(abs);
    }

    let filePath = pathname.replace(/^\/([A-Za-z]:[\\/])/, "$1");
    return p.resolve(p.normalize(filePath));
  } catch {
    let raw = decodePathname(requestUrl.replace(/^localfile:\/\//i, ""));
    raw = raw.replace(/^\/([A-Za-z]:[\\/])/, "$1");
    if (platform === "win32") {
      const m = raw.match(/^\/?([a-zA-Z])[:/][\\/]?(.*)$/);
      if (m) return p.resolve(`${m[1].toUpperCase()}:\\${m[2].replace(/\//g, "\\")}`);
    }
    if (!raw.startsWith("/") && !/^[A-Za-z]:[\\/]/.test(raw)) {
      raw = `/${raw}`;
    }
    if (platform === "darwin" && /^\/users\//i.test(raw)) {
      raw = "/Users" + raw.slice("/users".length);
    }
    return p.resolve(p.normalize(raw));
  }
}

/**
 * True when `filePath` is `root` or a descendant. Uses the platform path
 * module so Windows drive-letter case (`C:\` vs `c:\`) does not 403.
 */
export function isFsPathInside(
  filePath: string,
  root: string,
  platform: Platform = process.platform,
): boolean {
  const p = pathFor(platform);
  const resolvedFile = p.resolve(filePath);
  const resolvedRoot = p.resolve(root);
  const rel = p.relative(resolvedRoot, resolvedFile);
  return rel === "" || (Boolean(rel) && !rel.startsWith("..") && !p.isAbsolute(rel));
}

export function isLocalfileAllowed(
  filePath: string,
  allowedRoots: string[],
  platform: Platform = process.platform,
): boolean {
  return allowedRoots.some((root) => isFsPathInside(filePath, root, platform));
}
