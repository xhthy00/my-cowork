# Build Windows backend binary and smoke-start it.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location "$Root\backend"
uv sync
uv run pyinstaller "$Root\build\pyinstaller\windows.spec" --distpath "$Root\dist" --workpath "$Root\build\pyinstaller\work-windows" -y
$Bin = "$Root\dist\my-cowork-backend.exe"
New-Item -ItemType Directory -Force -Path "$Root\dist\win-python" | Out-Null
$env:MY_COWORK_API_KEY = if ($env:MY_COWORK_API_KEY) { $env:MY_COWORK_API_KEY } else { "smoke-test-key" }
$env:MY_COWORK_ENABLE_SCHEDULER = "0"
$Log = "$Root\build\pyinstaller\smoke-windows.log"
$proc = Start-Process -FilePath $Bin -ArgumentList "--port","8765" -RedirectStandardOutput $Log -RedirectStandardError $Log -PassThru
Start-Sleep -Seconds 5
$content = Get-Content $Log -Raw
if ($content -match "Uvicorn running|127\.0\.0\.1:") {
  Write-Host "SMOKE OK"
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  exit 0
}
Write-Host "SMOKE FAIL"
Write-Host $content
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
exit 1
