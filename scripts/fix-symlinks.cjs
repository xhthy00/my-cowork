#!/usr/bin/env node
/**
 * Make terminal_venv/bin/python* relative symlinks into ../uv_python
 * and replace absolute shebangs with placeholders (Eigent fix-symlinks.js).
 */

const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const venvPath = path.join(projectRoot, "resources", "prebuilt", "terminal_venv");
const uvPythonDir = path.join(projectRoot, "resources", "prebuilt", "uv_python");

function findPythonExecutable(dir) {
  if (!fs.existsSync(dir)) return null;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith("cpython-")) continue;
    const candidates = [
      path.join(dir, entry.name, "bin", "python3.10"),
      path.join(dir, entry.name, "bin", "python"),
      path.join(dir, entry.name, "install", "bin", "python3.10"),
      path.join(dir, entry.name, "install", "bin", "python"),
      path.join(dir, entry.name, "python.exe"),
    ];
    for (const p of candidates) {
      if (fs.existsSync(p)) {
        return { absolutePath: p, cpythonDir: entry.name };
      }
    }
  }
  return null;
}

function fixSymlinks() {
  const binDir = path.join(venvPath, "bin");
  const scriptsDir = path.join(venvPath, "Scripts");
  if (fs.existsSync(scriptsDir) && !fs.existsSync(binDir)) {
    console.log("Windows venv — skip symlink fixes");
    return true;
  }
  if (!fs.existsSync(binDir)) {
    console.log(`bin not found: ${binDir}`);
    return false;
  }

  const pythonInfo = findPythonExecutable(uvPythonDir);
  if (!pythonInfo) {
    console.log("No Python in uv_python");
    return false;
  }

  for (const name of ["python", "python3", "python3.10"]) {
    const symlinkPath = path.join(binDir, name);
    try {
      try {
        fs.lstatSync(symlinkPath);
        fs.unlinkSync(symlinkPath);
      } catch {
        /* missing */
      }
      const target =
        name === "python"
          ? path.relative(binDir, pythonInfo.absolutePath)
          : "python";
      fs.symlinkSync(target, symlinkPath);
      console.log(`${name} → ${target}`);
    } catch (err) {
      console.error(`Failed ${name}: ${err.message}`);
    }
  }
  return true;
}

function fixShebangs() {
  const binDir = path.join(venvPath, "bin");
  if (!fs.existsSync(binDir)) return 0;
  let fixed = 0;
  for (const entry of fs.readdirSync(binDir)) {
    const filePath = path.join(binDir, entry);
    let stat;
    try {
      stat = fs.lstatSync(filePath);
    } catch {
      continue;
    }
    if (stat.isDirectory() || stat.isSymbolicLink()) continue;

    const full = fs.readFileSync(filePath, "utf-8");
    const firstLine = full.split("\n")[0] || "";
    if (!firstLine.startsWith("#!") || !firstLine.includes("python")) continue;
    const shebangPath = firstLine.slice(2).trim();
    const hasVenvPath =
      firstLine.includes("/resources/prebuilt/terminal_venv/") ||
      firstLine.includes("\\resources\\prebuilt\\terminal_venv\\");
    if (!path.isAbsolute(shebangPath) && !hasVenvPath) continue;

    const next = full.replace(/^#!.*python.*$/m, "#!{{PREBUILT_VENV_PYTHON}}");
    if (next !== full) {
      fs.writeFileSync(filePath, next, "utf-8");
      fs.chmodSync(filePath, 0o755);
      fixed++;
    }
  }
  console.log(`Fixed ${fixed} shebang(s)`);
  return fixed;
}

function main() {
  console.log("Fixing terminal_venv symlinks / shebangs...");
  if (!fs.existsSync(venvPath)) {
    console.log("terminal_venv missing — skip (ok for pure-dev)");
    return;
  }
  fixSymlinks();
  fixShebangs();
}

main();
