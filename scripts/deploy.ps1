param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Environment = "dev",
  [string]$Region = "sa-east-1",
  [string]$OpenWeatherApiKeyParameterName = "",
  [int]$MonthlyOperationalCallLimit = 500000,
  [int]$RawDataRetentionDays = 30,
  [int]$LogRetentionDays = 7,
  [int]$MonthlyBudgetAmount = 10,
  [string]$BudgetAlertEmail = "",
  [ValidateSet("true", "false")][string]$EnableSchedules = "false",
  [ValidateSet("true", "false")][string]$EnableAirPollution = "true",
  [ValidateSet("true", "false")][string]$EnableFrontend = "true",
  [ValidateSet("true", "false")][string]$EnableAnalytics = "true",
  [ValidateSet(3, 5, 10, 15, 30)][int]$CurrentWeatherIntervalMinutes = 3,
  # Sync the OpenWeather key from -ApiKey, $env:OPENWEATHER_API_KEY or .env when the SSM parameter is missing.
  [string]$ApiKey = "",
  # Review the CloudFormation change set before applying it.
  [switch]$ConfirmChangeset,
  # Build with the local Python 3.13 instead of the SAM build container (Linux/CI only).
  [switch]$NoContainer,
  [switch]$SkipFrontend,
  # Run one collection of every product and publish the dashboard data right after the deploy.
  [switch]$RunInitialCollection
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $OpenWeatherApiKeyParameterName) {
  $OpenWeatherApiKeyParameterName = "/weather-data-pipeline/$Environment/openweather-api-key"
}

$overrides = @(
  "Environment=$Environment",
  "OpenWeatherApiKeyParameterName=$OpenWeatherApiKeyParameterName",
  "MonthlyOperationalCallLimit=$MonthlyOperationalCallLimit",
  "RawDataRetentionDays=$RawDataRetentionDays",
  "LogRetentionDays=$LogRetentionDays",
  "MonthlyBudgetAmount=$MonthlyBudgetAmount",
  "EnableSchedules=$EnableSchedules",
  "EnableAirPollution=$EnableAirPollution",
  "EnableFrontend=$EnableFrontend",
  "EnableAnalytics=$EnableAnalytics",
  "CurrentWeatherIntervalMinutes=$CurrentWeatherIntervalMinutes"
)
# sam rejects "Key=" with an empty value, so optional parameters are only sent when set.
if ($BudgetAlertEmail) { $overrides += "BudgetAlertEmail=$BudgetAlertEmail" }

if ($NoContainer) { sam build --no-use-container } else { sam build --use-container }
if ($LASTEXITCODE -ne 0) { throw "sam build failed" }

$deployArgs = @(
  "deploy",
  "--stack-name", $StackName,
  "--region", $Region,
  "--capabilities", "CAPABILITY_IAM",
  "--resolve-s3",
  "--no-fail-on-empty-changeset",
  "--parameter-overrides"
) + $overrides
if ($ConfirmChangeset) { $deployArgs += "--confirm-changeset" } else { $deployArgs += "--no-confirm-changeset" }
sam @deployArgs
if ($LASTEXITCODE -ne 0) { throw "sam deploy failed" }

# The API key lives only in SSM; create it on the first deploy when it is available locally.
# (Windows PowerShell 5.1 turns redirected native stderr into terminating errors under "Stop".)
$ErrorActionPreference = "Continue"
aws ssm get-parameter --name $OpenWeatherApiKeyParameterName --region $Region --query "Parameter.Name" --output text 2>$null | Out-Null
$parameterExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = "Stop"
if (-not $parameterExists) {
  if ($ApiKey -or $env:OPENWEATHER_API_KEY -or (Test-Path -LiteralPath ".env")) {
    ./scripts/set-openweather-key.ps1 -ApiKey $ApiKey -ParameterName $OpenWeatherApiKeyParameterName -Region $Region -FromEnvironment
  } else {
    Write-Warning "SSM parameter $OpenWeatherApiKeyParameterName not found. Run ./scripts/set-openweather-key.ps1 before collecting."
  }
} elseif ($ApiKey) {
  ./scripts/set-openweather-key.ps1 -ApiKey $ApiKey -ParameterName $OpenWeatherApiKeyParameterName -Region $Region
}

if (-not $SkipFrontend) {
  ./scripts/publish-frontend.ps1 -StackName $StackName -Region $Region
}

if ($RunInitialCollection) {
  ./scripts/invoke-planner.ps1 -StackName $StackName -Region $Region -Products all
  Write-Host "Waiting 90 seconds for the collector to drain the queue..."
  Start-Sleep -Seconds 90
  ./scripts/invoke-publisher.ps1 -StackName $StackName -Region $Region
  ./scripts/invoke-curator.ps1 -StackName $StackName -Region $Region -LookbackHours 1
}

./scripts/show-stack-outputs.ps1 -StackName $StackName -Region $Region
