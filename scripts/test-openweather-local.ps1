param(
  [string[]]$States = @("SP"),
  [string[]]$Products = @("current_weather"),
  [string]$EnvFile = ".env",
  [string]$ApiKey = "",
  [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  $python = "python"
}

$argsList = @(
  "scripts/local_openweather_check.py",
  "--states", ($States -join ","),
  "--products", ($Products -join ","),
  "--env-file", $EnvFile,
  "--timeout-seconds", "$TimeoutSeconds"
)

if ($ApiKey) {
  $argsList += @("--api-key", $ApiKey)
}

& $python @argsList
