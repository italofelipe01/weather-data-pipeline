param(
  [string]$TaskName = "WeatherDataPipelineOffline",
  [ValidateSet(3, 5, 10, 15, 30)][int]$IntervalMinutes = 3,
  [int]$Port = 8000,
  # Remove the scheduled task instead of creating it.
  [switch]$Uninstall
)

# Windows only: registers a Task Scheduler task that starts the offline service at logon, hidden,
# and restarts it if it stops. Logs go to .local-data/logs/offline-service.log.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Uninstall) {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "Task $TaskName removed."
  exit 0
}

$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw)) {
  throw "Create the virtual environment first: python -m venv .venv; .venv\Scripts\python -m pip install -r requirements-offline.txt"
}

$arguments = "scripts\offline_service.py --interval-minutes $IntervalMinutes --port $Port"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
  -TaskName $TaskName `
  -Description "Weather data pipeline (offline): OpenWeather collection, curation and dashboard at http://localhost:$Port" `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task $TaskName registered and started. Dashboard: http://localhost:$Port/"
Write-Host "Remove with: ./scripts/install-offline-service.ps1 -Uninstall"
