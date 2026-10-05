param(
  [string[]]$States = @(),
  [switch]$NoAirPollution,
  [switch]$Serve,
  [int]$Port = 8000
)

# One full cycle with the real API (collect every product, curate closed hours, publish), then exit.
# For continuous operation without AWS use ./scripts/start-offline.ps1.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

$argsList = @("scripts/offline_service.py", "--once")
if ($States.Count -gt 0) { $argsList += @("--states", ($States -join ",")) }
if ($NoAirPollution) { $argsList += "--no-air-pollution" }

& $python @argsList
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Serve) {
  Write-Host "Dashboard em http://localhost:$Port/ (Ctrl+C para parar)"
  & $python -m http.server $Port --directory frontend
}
