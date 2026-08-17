#!/usr/bin/env node
/**
 * Replace absolute home= paths in terminal_venv/pyvenv.cfg with
 * {{PREBUILT_PYTHON_DIR}} placeholders (Eigent fix-venv-paths.js).
 */

const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const venvPath = path.join(projectRoot, "resources", "prebuilt", "terminal_venv");
const pyvenvCfgPath = path.join(venvPath, "pyvenv.cfg");

function main() {
  console.log("Fixing pyvenv.cfg paths for portable terminal_venv...");
  if (!fs.existsSync(pyvenvCfgPath)) {
    console.log(`pyvenv.cfg not found: ${pyvenvCfgPath} (ok if not built yet)`);
    return;
  }

  let content = fs.readFileSync(pyvenvCfgPath, "utf-8");
  const homeMatch = content.match(/^home\s*=\s*(.+)$/m);
  if (!homeMatch) {
    console.error("No home= line in pyvenv.cfg");
    process.exit(1);
  }

  const originalHome = homeMatch[1].trim();
  if (originalHome.includes("{{PREBUILT_PYTHON_DIR}}")) {
    console.log("Already using placeholder");
    return;
  }

  const cpythonMatch = originalHome.match(/(cpython-[\w.-]+)(.*)/);
  if (!cpythonMatch) {
    console.error(`Could not extract cpython dir from: ${originalHome}`);
    process.exit(1);
  }

  const isWindowsPath =
    /^[A-Za-z]:\\/.test(originalHome) ||
    originalHome.startsWith("\\\\") ||
    originalHome.includes("\\");
  const pathSep = isWindowsPath ? "\\" : "/";
  const newHome = `{{PREBUILT_PYTHON_DIR}}${pathSep}${cpythonMatch[1]}${cpythonMatch[2]}`;
  content = content.replace(/^home\s*=\s*.+$/m, `home = ${newHome}`);
  fs.writeFileSync(pyvenvCfgPath, content);
  console.log(`Updated home → ${newHome}`);
}

main();
