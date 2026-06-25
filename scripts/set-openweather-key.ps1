param(
  [Parameter(Mandatory = $true)]
  [string]$ApiKey,
  [string]$Environment = "dev",
  [string]$Region = "sa-east-1",
  [string]$ParameterName = ""
)

$ErrorActionPreference = "Stop"

if (-not $ParameterName) {
  $ParameterName = "/weather-data-pipeline/$Environment/openweather-api-key"
}

aws ssm put-parameter `
  --name $ParameterName `
  --type "SecureString" `
  --value $ApiKey `
  --overwrite `
  --region $Region | Out-Null

Write-Host "OpenWeather API key stored in $ParameterName"
