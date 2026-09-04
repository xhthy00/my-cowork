# One-shot Windows packaging for MyCowork.
#
# Default (fast): reuse existing python_runtime / prebuilt / officecli when present,
# then npm build + electron-builder NSIS installer.
#
# Usage:
#   .\scripts\build-windows.ps1                 # smart skip
#   .\scripts\build-windows.ps1 -Full           # rebuild everything
#   .\scripts\build-windows.ps1 -SkipPython     # never rebuild backend
#   npm run package:win
#
param(
  [switch]$Full,
  [switch]$SkipPython,
  [switch]$SkipTerminalDeps,
  [switch]$SkipOfficeCli,
  [switch]$NoNvmSwitch,
  [string]$NodeVersion = "21.7.3",
  [string]$RestoreNodeVersion = "16.20.2",
  [string]$NvmHome = $(if ($env:NVM_HOME) { $env:NVM_HOME } else { "D:\software\nvm" }),
  [string]$NodeSymlink = $(if ($env:NVM_SYMLINK) { $env:NVM_SYMLINK } else { "D:\develop\nodejs" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Step([string]$Msg) {
  Write-Host ""
  Write-Host "==> $Msg" -ForegroundColor Cyan
}

function Test-PathExists([string]$Path, [string]$Label) {
  if (-not (Test-Path $Path)) {
    throw "Missing $Label`: $Path"
  }
}

function Stop-PackagedProcesses {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ExecutablePath -and (
      $_.ExecutablePath -match "python_runtime\\python\.exe" `
      -or $_.ExecutablePath -match "MyCowork\.exe" `
      -or $_.ExecutablePath -match "my-cowork-backend"
    )
  } | ForEach-Object {
    Write-Host "Stopping PID $($_.ProcessId): $($_.Name)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

function Invoke-BashScript([string]$RelPath) {
  $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
  $bashCandidates = @(
    $(if ($bashCmd) { $bashCmd.Source }),
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe"
  ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

  if (-not $bashCandidates) {
    throw "Git Bash not found; install Git for Windows or run fetch manually."
  }
  $bash = $bashCandidates[0]
  Write-Host "Using bash: $bash"
  & $bash $RelPath
  if ($LASTEXITCODE -ne 0) { throw "bash $RelPath failed with exit $LASTEXITCODE" }
}

function Use-NvmNode([string]$Version) {
  if ($NoNvmSwitch) {
    Write-Host "Skipping nvm (NoNvmSwitch); using current node: $(node -v 2>$null)"
    return
  }
  $nvmExe = Join-Path $NvmHome "nvm.exe"
  if (-not (Test-Path $nvmExe)) {
    Write-Warning "nvm.exe not found at $nvmExe; using current node on PATH"
    return
  }
  Write-Host "nvm use $Version"
  & $nvmExe use $Version | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "nvm use $Version failed" }
  $env:Path = "$NodeSymlink;$NvmHome\v$Version;" + $env:Path
  Write-Host "node $(node -v)  npm $(npm -v)"
}

# ── resolve skip flags ────────────────────────────────────────────────────────
$pythonExe = Join-Path $Root "dist\python_runtime\python.exe"
$terminalMarker = Join-Path $Root "resources\prebuilt\terminal_venv\.packages_installed"
$officeCli = Join-Path $Root "resources\bin\officecli.exe"

if ($Full) {
  $SkipPython = $false
  $SkipTerminalDeps = $false
  $SkipOfficeCli = $false
} else {
  if (-not $PSBoundParameters.ContainsKey("SkipPython") -and (Test-Path $pythonExe)) {
    $SkipPython = $true
    Write-Host "Reuse existing backend: $pythonExe"
  }
  if (-not $PSBoundParameters.ContainsKey("SkipTerminalDeps") -and (Test-Path $terminalMarker)) {
    $SkipTerminalDeps = $true
    Write-Host "Reuse existing terminal prebuilt: $terminalMarker"
  }
  if (-not $PSBoundParameters.ContainsKey("SkipOfficeCli") -and (Test-Path $officeCli)) {
    $SkipOfficeCli = $true
    Write-Host "Reuse existing OfficeCLI: $officeCli"
  }
}

Write-Step "MyCowork Windows package (Root=$Root)"
Write-Host "SkipPython=$SkipPython SkipTerminalDeps=$SkipTerminalDeps SkipOfficeCli=$SkipOfficeCli Full=$Full"

Stop-PackagedProcesses
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"

Use-NvmNode $NodeVersion

try {
  if (-not $SkipOfficeCli) {
    Write-Step "Fetch OfficeCLI"
    $env:OFFICECLI_PLATFORM = "win-x64"
    Invoke-BashScript (Join-Path $Root "scripts\fetch-officecli.sh")
  } else {
    Test-PathExists $officeCli "OfficeCLI"
  }

  if (-not $SkipTerminalDeps) {
    Write-Step "Prebuild terminal Python (resources/prebuilt)"
    $env:UV_LINK_MODE = "copy"
    npm run prebuild:terminal-deps
    if ($LASTEXITCODE -ne 0) { throw "prebuild:terminal-deps failed" }
  } else {
    Test-PathExists $terminalMarker "terminal prebuilt marker"
  }

  if (-not $SkipPython) {
    Write-Step "Build Python backend (PyInstaller onedir)"
    & (Join-Path $Root "scripts\build-python-windows.ps1")
    if ($LASTEXITCODE -ne 0) { throw "build-python-windows failed" }
  } else {
    Test-PathExists $pythonExe "packaged backend"
  }

  Write-Step "Verify extraResources"
  Test-PathExists $pythonExe "dist/python_runtime/python.exe"
  Test-PathExists $officeCli "resources/bin/officecli.exe"
  Test-PathExists (Join-Path $Root "resources\prebuilt") "resources/prebuilt"
  Test-PathExists (Join-Path $Root "build\icon.ico") "build/icon.ico"

  Write-Step "Build renderer + electron main (tsc + vite)"
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }

  Write-Step "electron-builder (NSIS installer)"
  npx electron-builder --config build/electron-builder.yml --win nsis --publish never
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed" }

  Write-Step "Done"
  Get-ChildItem (Join-Path $Root "release") -Filter "MyCowork Setup*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object {
      Write-Host "Installer: $($_.FullName) ($([math]::Round($_.Length/1MB,1)) MB)" -ForegroundColor Green
    }
}
finally {
  if (-not $NoNvmSwitch) {
    Write-Step "Restore Node $RestoreNodeVersion"
    Use-NvmNode $RestoreNodeVersion
  }
}
