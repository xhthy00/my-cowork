/**
 * Copy NSIS progress patches into electron-builder templates before pack.
 * Default templates hide details and extract 7z without progress callbacks.
 */
const fs = require("fs");
const path = require("path");

module.exports = async function beforeBuild() {
  const root = path.join(__dirname, "..");
  const nsis = path.join(
    root,
    "node_modules",
    "app-builder-lib",
    "templates",
    "nsis",
  );
  const srcDir = path.join(root, "build", "nsis");
  const copies = [
    ["extractAppPackage.nsh", path.join(nsis, "include", "extractAppPackage.nsh")],
    ["installSection.nsh", path.join(nsis, "installSection.nsh")],
  ];
  for (const [name, dest] of copies) {
    const src = path.join(srcDir, name);
    if (!fs.existsSync(src) || !fs.existsSync(path.dirname(dest))) {
      throw new Error(`NSIS patch missing: ${src} -> ${dest}`);
    }
    fs.copyFileSync(src, dest);
  }
};
