# Bundled OfficeCLI

`scripts/fetch-officecli.sh` downloads the platform binary here as `officecli` (or `officecli.exe` on Windows).

- Dev: run `bash scripts/fetch-officecli.sh` once (or after clearing this folder).
- Release: `scripts/build-electron.sh` / CI call the fetch script before packaging.
- Runtime: Electron sets `MY_COWORK_OFFICECLI` to `resources/bin/officecli` (dev) or `process.resourcesPath/bin/officecli` (packaged).
