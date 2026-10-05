param(
  [ValidateSet(3, 5, 10, 15, 30)][int]$IntervalMinutes = 3,
  [int]$Port = 8000,
  [string[]]$States = @(),
  [switch]$NoAirPollution,
  [int]$RawRetentionDays = 30,
  # Listen on all interfaces so phones and other computers on the network can open the dashboard.
  [switch]$Lan
)

# Runs the full pipeline on this machine until Ctrl+C: collection on the cloud cadence, curation,
# dashboard at http://localhost:<Port>. No AWS account needed; only the OpenWeather key in .env.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

$argsList = @(
  "scripts/offline_service.py",
  "--interval-minutes", "$IntervalMinutes",
  "--port", "$Port",
  "--raw-retention-days", "$RawRetentionDays"
)
if ($States.Count -gt 0) { $argsList += @("--states", ($States -join ",")) }
if ($NoAirPollution) { $argsList += "--no-air-pollution" }
if ($Lan) { $argsList += @("--host", "0.0.0.0") }

& $python @argsList
exit $LASTEXITCODE
