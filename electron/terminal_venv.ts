/**
 * Eigent-aligned terminal Python: ensure/copy terminal_base venv under ~/.my-cowork.
 */
import { execFileSync, execSync, spawnSync } from "child_process";
import { app } from "electron";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

export const TERMINAL_BASE_PACKAGES = [
  "pandas",
  "numpy",
  "matplotlib",
  "requests",
  "openpyxl",
  "beautifulsoup4",
  "pillow",
  "plotly",
];

const TERMINAL_VENV_VERSION_FILE = ".terminal_venv_version";
const APP_DIR_NAME = ".my-cowork";

function log(msg: string): void {
  console.log(`[terminal-venv] ${msg}`);
}

function warn(msg: string): void {
  console.warn(`[terminal-venv] ${msg}`);
}

export function getAppHome(): string {
  return path.join(os.homedir(), APP_DIR_NAME);
}

export function getVenvsBaseDir(): string {
  return path.join(getAppHome(), "venvs");
}

export function getUserTerminalBasePath(version: string): string {
  return path.join(getVenvsBaseDir(), `terminal_base-${version}`);
}

export function getVenvPythonPath(venvPath: string): string {
  return process.platform === "win32"
    ? path.join(venvPath, "Scripts", "python.exe")
    : path.join(venvPath, "bin", "python");
}

export function getPrebuiltPythonDir(): string | null {
  if (!app.isPackaged) return null;
  const dir = path.join(process.resourcesPath, "prebuilt", "uv_python");
  return fs.existsSync(dir) ? dir : null;
}

function getPrebuiltTerminalVenvSrc(): string | null {
  if (!app.isPackaged) return null;
  const dir = path.join(process.resourcesPath, "prebuilt", "terminal_venv");
  const marker = path.join(dir, ".packages_installed");
  if (!fs.existsSync(dir) || !fs.existsSync(marker)) return null;
  return dir;
}

function findPythonInUvPython(uvPythonDir: string): string | null {
  if (!fs.existsSync(uvPythonDir)) return null;
  const candidates: string[] = [];
  try {
    for (const entry of fs.readdirSync(uvPythonDir, { withFileTypes: true })) {
      if (!entry.isDirectory() || !entry.name.startsWith("cpython-")) continue;
      const sub = path.join(uvPythonDir, entry.name);
      candidates.push(
        path.join(sub, "bin", "python3.10"),
        path.join(sub, "bin", "python3"),
        path.join(sub, "bin", "python"),
        path.join(sub, "install", "bin", "python3.10"),
        path.join(sub, "install", "bin", "python"),
        path.join(sub, "python.exe"),
      );
    }
  } catch {
    /* ignore */
  }
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function getActualPythonPathFromPyvenvCfg(venvPath: string): string | null {
  const cfg = path.join(venvPath, "pyvenv.cfg");
  if (!fs.existsSync(cfg)) return null;
  const content = fs.readFileSync(cfg, "utf-8");
  const homeMatch = content.match(/^home\s*=\s*(.+)$/m);
  if (!homeMatch) return null;
  const home = homeMatch[1].trim();
  if (!path.isAbsolute(home) || !fs.existsSync(home)) return null;
  try {
    const entries = fs.readdirSync(home);
    const py = entries.find(
      (e) => e === "python3" || (e.startsWith("python3.") && !e.endsWith(".py")),
    );
    if (py) {
      const full = path.join(home, py);
      if (fs.existsSync(full)) return full;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function fixPyvenvCfgPlaceholder(pyvenvCfgPath: string): boolean {
  try {
    let content = fs.readFileSync(pyvenvCfgPath, "utf-8");
    if (!content.includes("{{PREBUILT_PYTHON_DIR}}")) return true;

    const prebuilt =
      getPrebuiltPythonDir() ||
      (fs.existsSync(path.join(getAppHome(), "uv_python"))
        ? path.join(getAppHome(), "uv_python")
        : null);
    if (!prebuilt) {
      warn("Cannot fix pyvenv.cfg: prebuilt Python missing");
      return false;
    }
    content = content.replace(/\{\{PREBUILT_PYTHON_DIR\}\}/g, prebuilt);
    fs.writeFileSync(pyvenvCfgPath, content);
    log(`Fixed pyvenv.cfg with ${prebuilt}`);
    return true;
  } catch (e) {
    warn(`Failed to fix pyvenv.cfg: ${e}`);
    return false;
  }
}

function fixVenvScriptShebangs(venvPath: string): boolean {
  if (process.platform === "win32") return true;
  const binDir = path.join(venvPath, "bin");
  if (!fs.existsSync(binDir)) return false;

  const actualPython =
    getActualPythonPathFromPyvenvCfg(venvPath) ||
    findPythonInUvPython(getPrebuiltPythonDir() || path.join(getAppHome(), "uv_python"));

  let fixed = 0;
  for (const entry of fs.readdirSync(binDir)) {
    const filePath = path.join(binDir, entry);
    try {
      const st = fs.lstatSync(filePath);
      if (st.isDirectory() || st.isSymbolicLink()) continue;
    } catch {
      continue;
    }
    try {
      const content = fs.readFileSync(filePath, "utf-8");
      const firstLine = content.split("\n")[0];
      if (!firstLine?.startsWith("#!")) continue;
      let next = content;
      if (content.includes("{{PREBUILT_VENV_PYTHON}}") && actualPython) {
        next = next.replace(/\{\{PREBUILT_VENV_PYTHON\}\}/g, actualPython);
      }
      if (content.includes("{{PREBUILT_PYTHON_DIR}}")) {
        const prebuilt = getPrebuiltPythonDir() || path.join(getAppHome(), "uv_python");
        next = next.replace(/\{\{PREBUILT_PYTHON_DIR\}\}/g, prebuilt);
      }
      const shebangPath = firstLine.slice(2).trim();
      if (actualPython && shebangPath && !shebangPath.startsWith("{{")) {
        const resolved = path.resolve(path.dirname(filePath), shebangPath);
        if (!fs.existsSync(resolved)) {
          next = next.replace(/^#!.*$/m, `#!${actualPython}`);
        }
      }
      if (next !== content) {
        fs.writeFileSync(filePath, next, "utf-8");
        fs.chmodSync(filePath, 0o755);
        fixed++;
      }
    } catch {
      /* skip */
    }
  }
  if (fixed > 0) log(`Fixed shebangs in ${fixed} script(s)`);
  return true;
}

function ensureVenvPythonSymlink(venvPath: string): boolean {
  if (process.platform === "win32") return true;
  const binDir = path.join(venvPath, "bin");
  const pythonPath = path.join(binDir, "python");
  if (!fs.existsSync(binDir)) return false;

  try {
    fs.accessSync(pythonPath, fs.constants.X_OK);
    return true;
  } catch {
    log(`python missing/broken at ${pythonPath}, creating symlink...`);
  }

  const actualPython = getActualPythonPathFromPyvenvCfg(venvPath);
  try {
    try {
      fs.lstatSync(pythonPath);
      fs.unlinkSync(pythonPath);
    } catch {
      /* missing */
    }
    if (!actualPython || !fs.existsSync(actualPython)) {
      warn("No valid Python target for symlink");
      return false;
    }
    fs.symlinkSync(actualPython, pythonPath);
    try {
      fs.chmodSync(pythonPath, 0o755);
    } catch {
      /* ignore */
    }
    log(`Created python symlink → ${actualPython}`);
    return true;
  } catch (e) {
    warn(`Failed to create python symlink: ${e}`);
    return false;
  }
}

function findUv(): string | null {
  try {
    const which = process.platform === "win32" ? "where" : "which";
    const out = execFileSync(which, ["uv"], { encoding: "utf-8" }).trim();
    return out.split(/\r?\n/)[0]?.trim() || null;
  } catch {
    return null;
  }
}

/**
 * Packaged: copy Resources/prebuilt/terminal_venv → ~/.my-cowork/venvs/terminal_base-{version}.
 */
export function ensureTerminalVenvAtUserPath(version: string): void {
  if (!app.isPackaged) return;

  const prebuiltTerminalVenv = getPrebuiltTerminalVenvSrc();
  const prebuiltUvPython = getPrebuiltPythonDir();
  if (!prebuiltTerminalVenv) return;

  const userVenvsDir = getVenvsBaseDir();
  const userTerminalVenv = getUserTerminalBasePath(version);
  const userVenvMarker = path.join(userTerminalVenv, ".packages_installed");
  const versionFile = path.join(userVenvsDir, TERMINAL_VENV_VERSION_FILE);

  const userUvPython = path.join(getAppHome(), "uv_python");
  if (!fs.existsSync(userUvPython) && prebuiltUvPython) {
    try {
      fs.mkdirSync(path.dirname(userUvPython), { recursive: true });
      fs.symlinkSync(prebuiltUvPython, userUvPython);
      log(`Created uv_python symlink: ${userUvPython}`);
    } catch (e) {
      warn(`Failed to create uv_python symlink: ${e}`);
    }
  }

  if (fs.existsSync(userVenvMarker)) {
    const stored = fs.existsSync(versionFile)
      ? fs.readFileSync(versionFile, "utf-8").trim()
      : null;
    if (stored === version) {
      log(`Terminal venv already at ${userTerminalVenv} (v${version})`);
      return;
    }
  }

  log(`Copying prebuilt terminal venv to ${userTerminalVenv}...`);
  try {
    fs.mkdirSync(userVenvsDir, { recursive: true });
    if (fs.existsSync(userTerminalVenv)) {
      fs.rmSync(userTerminalVenv, { recursive: true, force: true });
    }
    fs.cpSync(prebuiltTerminalVenv, userTerminalVenv, {
      recursive: true,
      verbatimSymlinks: true,
    });
    fixPyvenvCfgPlaceholder(path.join(userTerminalVenv, "pyvenv.cfg"));
    fixVenvScriptShebangs(userTerminalVenv);
    ensureVenvPythonSymlink(userTerminalVenv);
    if (process.platform === "darwin") {
      try {
        execSync(`xattr -cr "${userTerminalVenv}"`, { stdio: "ignore" });
      } catch {
        /* ignore */
      }
    }
    fs.writeFileSync(versionFile, version, "utf-8");
    log("Terminal venv copied successfully");
  } catch (error) {
    warn(`Failed to copy terminal venv: ${error}`);
  }
}

/**
 * Dev / no-prebuilt: create ~/.my-cowork/venvs/terminal_base-{version} via uv.
 */
export function installTerminalBaseVenv(version: string): boolean {
  const terminalVenvPath = getUserTerminalBasePath(version);
  const pythonPath = getVenvPythonPath(terminalVenvPath);
  const marker = path.join(terminalVenvPath, ".packages_installed");

  if (fs.existsSync(pythonPath) && fs.existsSync(marker)) {
    log("Terminal base venv already exists with packages");
    return true;
  }

  const uv = findUv();
  if (!uv) {
    warn("uv not found; cannot install terminal base venv");
    return false;
  }

  const cacheDir = path.join(getAppHome(), "cache", "uv_python");
  fs.mkdirSync(cacheDir, { recursive: true });
  const env = {
    ...process.env,
    UV_PYTHON_INSTALL_DIR: cacheDir,
    UV_HTTP_TIMEOUT: "300",
  };

  const needsPkgs = fs.existsSync(pythonPath) && !fs.existsSync(marker);
  try {
    if (!needsPkgs) {
      fs.mkdirSync(path.dirname(terminalVenvPath), { recursive: true });
      log(`Creating terminal base venv at ${terminalVenvPath}`);
      const r = spawnSync(uv, ["venv", "--python", "3.10", terminalVenvPath], {
        env,
        encoding: "utf-8",
      });
      if (r.status !== 0) {
        warn(`uv venv failed: ${r.stderr || r.stdout}`);
        return false;
      }
    }
    log(`Installing packages: ${TERMINAL_BASE_PACKAGES.join(", ")}`);
    const r2 = spawnSync(
      uv,
      ["pip", "install", "--python", pythonPath, ...TERMINAL_BASE_PACKAGES],
      { env, encoding: "utf-8" },
    );
    if (r2.status !== 0) {
      warn(`uv pip install failed: ${r2.stderr || r2.stdout}`);
      return false;
    }
    fs.writeFileSync(marker, new Date().toISOString());
    const versionFile = path.join(getVenvsBaseDir(), TERMINAL_VENV_VERSION_FILE);
    fs.mkdirSync(getVenvsBaseDir(), { recursive: true });
    fs.writeFileSync(versionFile, version, "utf-8");
    log("Terminal base venv installed");
    return true;
  } catch (e) {
    warn(`installTerminalBaseVenv failed: ${e}`);
    return false;
  }
}

export async function cleanupOldVenvs(currentVersion: string): Promise<void> {
  const base = getVenvsBaseDir();
  if (!fs.existsSync(base)) return;
  for (const entry of fs.readdirSync(base, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    if (!entry.name.startsWith("terminal_base-")) continue;
    const ver = entry.name.slice("terminal_base-".length);
    if (ver === currentVersion) continue;
    const full = path.join(base, entry.name);
    try {
      fs.rmSync(full, { recursive: true, force: true });
      log(`Removed old venv ${entry.name}`);
    } catch (e) {
      warn(`Failed to remove ${entry.name}: ${e}`);
    }
  }
}

/**
 * Ensure terminal_base is ready (packaged copy or dev uv install) and return its path if usable.
 */
/**
 * App version from project package.json (not Electron's app.getVersion()).
 * Dev launches via `electron dist-electron/main.js` make getVersion() return
 * the Electron runtime version (e.g. 35.7.5) — wrong for terminal_base-*.
 */
export function getPackageVersion(): string {
  try {
    const pkgPath = path.join(__dirname, "..", "package.json");
    const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8")) as {
      version?: string;
    };
    if (pkg.version && typeof pkg.version === "string") return pkg.version;
  } catch {
    /* fall through */
  }
  try {
    return app.getVersion();
  } catch {
    return "0.1.0";
  }
}

/** Reuse a misplaced terminal_base-* (e.g. created under Electron version) once. */
function adoptMisnamedTerminalBase(version: string): void {
  const target = getUserTerminalBasePath(version);
  if (fs.existsSync(getVenvPythonPath(target))) return;
  const base = getVenvsBaseDir();
  if (!fs.existsSync(base)) return;
  for (const name of fs.readdirSync(base)) {
    if (!name.startsWith("terminal_base-") || name === `terminal_base-${version}`) {
      continue;
    }
    const candidate = path.join(base, name);
    const marker = path.join(candidate, ".packages_installed");
    if (!fs.existsSync(getVenvPythonPath(candidate)) || !fs.existsSync(marker)) {
      continue;
    }
    try {
      fs.mkdirSync(base, { recursive: true });
      fs.renameSync(candidate, target);
      fs.writeFileSync(
        path.join(base, TERMINAL_VENV_VERSION_FILE),
        version,
        "utf-8",
      );
      log(`Adopted ${name} → terminal_base-${version}`);
      return;
    } catch (e) {
      warn(`Failed to adopt ${name}: ${e}`);
    }
  }
}

export function prepareTerminalPython(version: string): string | null {
  adoptMisnamedTerminalBase(version);
  if (app.isPackaged) {
    ensureTerminalVenvAtUserPath(version);
  } else {
    installTerminalBaseVenv(version);
  }
  void cleanupOldVenvs(version);

  const base = getUserTerminalBasePath(version);
  const py = getVenvPythonPath(base);
  if (fs.existsSync(py)) return base;
  return null;
}
