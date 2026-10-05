param(
  # Optional: when omitted the key is read from $env:OPENWEATHER_API_KEY, then .env, then a hidden prompt.
  [string]$ApiKey = "",
  [string]$Environment = "dev",
  [string]$Region = "sa-east-1",
  [string]$ParameterName = "",
  [string]$EnvFile = ".env",
  # Never prompt; fail when no key is found (used by deploy.ps1).
  [switch]$FromEnvironment
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $ParameterName) {
  $ParameterName = "/weather-data-pipeline/$Environment/openweather-api-key"
}

if (-not $ApiKey) { $ApiKey = $env:OPENWEATHER_API_KEY }
if (-not $ApiKey -and (Test-Path -LiteralPath $EnvFile)) {
  $line = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^\s*OPENWEATHER_API_KEY\s*=' } | Select-Object -First 1
  if ($line) { $ApiKey = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'") }
}
if (-not $ApiKey -or $ApiKey -eq "SUA_API_KEY_AQUI") {
  if ($FromEnvironment) { throw "OpenWeather API key not found in -ApiKey, OPENWEATHER_API_KEY or $EnvFile." }
  $secure = Read-Host -Prompt "OpenWeather API key" -AsSecureString
  $ApiKey = [System.Net.NetworkCredential]::new("", $secure).Password
}
if (-not $ApiKey) { throw "OpenWeather API key is empty." }

# Pass the value through a temporary file so the key never shows up in the process list.
$valueFile = New-TemporaryFile
try {
  Set-Content -LiteralPath $valueFile -Value $ApiKey -NoNewline -Encoding ascii
  aws ssm put-parameter `
    --name $ParameterName `
    --type "SecureString" `
    --value "file://$($valueFile.FullName)" `
    --overwrite `
    --region $Region | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "aws ssm put-parameter failed" }
} finally {
  Remove-Item -LiteralPath $valueFile -Force -ErrorAction SilentlyContinue
}

Write-Host "OpenWeather API key stored in $ParameterName (the Collector picks it up within 5 minutes, no redeploy needed)."
