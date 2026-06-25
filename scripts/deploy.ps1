param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Environment = "dev",
  [string]$Region = "sa-east-1",
  [string]$OpenWeatherApiKeyParameterName = "/weather-data-pipeline/dev/openweather-api-key",
  [int]$MonthlyOperationalCallLimit = 500000,
  [int]$RawDataRetentionDays = 30,
  [int]$LogRetentionDays = 7,
  [int]$MonthlyBudgetAmount = 10,
  [string]$BudgetAlertEmail = "",
  [string]$EnableSchedules = "false"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

sam build
sam deploy `
  --stack-name $StackName `
  --region $Region `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    Environment=$Environment `
    OpenWeatherApiKeyParameterName=$OpenWeatherApiKeyParameterName `
    MonthlyOperationalCallLimit=$MonthlyOperationalCallLimit `
    RawDataRetentionDays=$RawDataRetentionDays `
    LogRetentionDays=$LogRetentionDays `
    MonthlyBudgetAmount=$MonthlyBudgetAmount `
    BudgetAlertEmail=$BudgetAlertEmail `
    EnableSchedules=$EnableSchedules

./scripts/show-stack-outputs.ps1 -StackName $StackName -Region $Region
