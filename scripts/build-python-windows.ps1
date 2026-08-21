# Build Windows backend binary and smoke-start it.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location "$Root\backend"
uv sync
uv run pyinstaller "$Root\build\pyinstaller\windows.spec" --distpath "$Root\dist" --workpath "$Root\build\pyinstaller\work-windows" -y
$Bin = "$Root\dist\my-cowork-backend.exe"
if (-not (Test-Path $Bin)) {
  Write-Host "binary missing: $Bin"
  Get-ChildItem "$Root\dist" -ErrorAction SilentlyContinue
  exit 1
}
Get-Item $Bin | Format-List FullName, Length
New-Item -ItemType Directory -Force -Path "$Root\dist\win-python" | Out-Null
$env:MY_COWORK_API_KEY = if ($env:MY_COWORK_API_KEY) { $env:MY_COWORK_API_KEY } else { "smoke-test-key" }
$env:MY_COWORK_ENABLE_SCHEDULER = "0"
$env:MY_COWORK_CHANNEL_AUTOSTART = "0"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONFAULTHANDLER = "1"
New-Item -ItemType Directory -Force -Path "$Root\build\pyinstaller" | Out-Null
$Log = "$Root\build\pyinstaller\smoke-windows.log"
$ErrLog = "$Root\build\pyinstaller\smoke-windows.err.log"
Remove-Item $Log, $ErrLog -ErrorAction SilentlyContinue
# stdout and stderr cannot share one file on Windows Start-Process
$proc = Start-Process -FilePath $Bin -ArgumentList "--port","8765" -RedirectStandardOutput $Log -RedirectStandardError $ErrLog -PassThru -WindowStyle Hidden

$healthy = $false
for ($i = 0; $i -lt 180; $i++) {
  if ($proc.HasExited) {
    Write-Host "backend exited before becoming healthy, code=$($proc.ExitCode)"
    break
  }
  try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 2
    if ($resp.StatusCode -eq 200) {
      $healthy = $true
      break
    }
  } catch {}
  Start-Sleep -Seconds 1
}

$out = ""
$err = ""
if (Test-Path $Log) { $out = Get-Content $Log -Raw -ErrorAction SilentlyContinue }
if (Test-Path $ErrLog) { $err = Get-Content $ErrLog -Raw -ErrorAction SilentlyContinue }
$content = "$out`n$err"
if ($healthy -or $content -match "Uvicorn running|127\.0\.0\.1:") {
  Write-Host "SMOKE OK"
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  exit 0
}
Write-Host "SMOKE FAIL"
Write-Host $content
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
exit 1
