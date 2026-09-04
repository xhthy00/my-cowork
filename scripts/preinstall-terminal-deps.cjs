#!/usr/bin/env node
/**
 * Build-time: install managed CPython + terminal_venv into resources/prebuilt.
 * Mirrors Eigent scripts/preinstall-deps.js (terminal portion only).
 */

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const PREBUILT_DIR = path.join(projectRoot, "resources", "prebuilt");
const TERMINAL_VENV_DIR = path.join(PREBUILT_DIR, "terminal_venv");
const UV_PYTHON_CACHE = path.join(PREBUILT_DIR, "cache", "uv_python");
const UV_PYTHON_BUNDLE = path.join(PREBUILT_DIR, "uv_python");

const TERMINAL_BASE_PACKAGES = [
  "pandas",
  "numpy",
  "matplotlib",
  "requests",
  "openpyxl",
  "beautifulsoup4",
  "pillow",
  "plotly",
];

function findUv() {
  try {
    const which = process.platform === "win32" ? "where" : "which";
    const out = execFileSync(which, ["uv"], { encoding: "utf-8" }).trim();
    return out.split(/\r?\n/)[0].trim();
  } catch {
    throw new Error("uv not found on PATH; install uv to build terminal Python");
  }
}

function copyDirRecursiveSync(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isSymbolicLink()) {
      // Windows often cannot create symlinks without admin; packaged apps
      // also prefer a real copy so extraResources stay portable.
      const target = fs.realpathSync(s);
      const st = fs.statSync(target);
      if (st.isDirectory()) copyDirRecursiveSync(target, d);
      else fs.copyFileSync(target, d);
    } else if (entry.isDirectory()) {
      copyDirRecursiveSync(s, d);
    } else {
      fs.copyFileSync(s, d);
    }
  }
}

function pythonInVenv(venvDir) {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function main() {
  console.log("Installing terminal prebuilt deps...");
  const uvPath = findUv();
  fs.mkdirSync(UV_PYTHON_CACHE, { recursive: true });

  const env = {
    ...process.env,
    UV_PYTHON_INSTALL_DIR: UV_PYTHON_CACHE,
    UV_HTTP_TIMEOUT: "300",
  };

  console.log("Ensuring managed Python 3.10...");
  execFileSync(uvPath, ["python", "install", "3.10"], {
    env,
    stdio: "inherit",
  });

  console.log(`Bundling uv_python → ${UV_PYTHON_BUNDLE}`);
  if (fs.existsSync(UV_PYTHON_BUNDLE)) {
    fs.rmSync(UV_PYTHON_BUNDLE, { recursive: true, force: true });
  }
  copyDirRecursiveSync(UV_PYTHON_CACHE, UV_PYTHON_BUNDLE);

  const pythonPath = pythonInVenv(TERMINAL_VENV_DIR);
  const marker = path.join(TERMINAL_VENV_DIR, ".packages_installed");
  const pyvenvCfg = path.join(TERMINAL_VENV_DIR, "pyvenv.cfg");

  if (fs.existsSync(pyvenvCfg)) {
    const content = fs.readFileSync(pyvenvCfg, "utf-8");
    if (content.includes("{{PREBUILT_PYTHON_DIR}}")) {
      console.log("Removing terminal_venv with placeholder from prior build...");
      fs.rmSync(TERMINAL_VENV_DIR, { recursive: true, force: true });
    }
  }

  if (fs.existsSync(pythonPath) && fs.existsSync(marker)) {
    console.log("Terminal base venv already present with packages");
  } else {
    const needsPkgs = fs.existsSync(pythonPath) && !fs.existsSync(marker);
    if (!needsPkgs) {
      fs.mkdirSync(TERMINAL_VENV_DIR, { recursive: true });
      console.log("Creating terminal_venv...");
      execFileSync(uvPath, ["venv", "--python", "3.10", TERMINAL_VENV_DIR], {
        env,
        stdio: "inherit",
      });
    }
    console.log(`Installing: ${TERMINAL_BASE_PACKAGES.join(", ")}`);
    execFileSync(
      uvPath,
      ["pip", "install", "--python", pythonPath, ...TERMINAL_BASE_PACKAGES],
      { env, stdio: "inherit" },
    );
    fs.writeFileSync(marker, new Date().toISOString());
  }

  console.log("Terminal prebuilt deps ready.");
  console.log(`  uv_python: ${UV_PYTHON_BUNDLE}`);
  console.log(`  terminal_venv: ${TERMINAL_VENV_DIR}`);
}

main();
