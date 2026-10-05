param(
  [int]$Hours = 36,
  [int]$HistoryDays = 400,
  [int]$Port = 8000,
  [switch]$NoServe
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

# Synthetic data only: no AWS account and no OpenWeather key needed.
& $python scripts/sample_data.py --hours $Hours --history-days $HistoryDays
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $NoServe) {
  Write-Host "Dashboard em http://localhost:$Port/ (Ctrl+C para parar)"
  & $python -m http.server $Port --directory frontend
}
