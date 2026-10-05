param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1",
  [string]$PayloadFile = "events/planner-event.json",
  # Overrides PayloadFile, e.g. -Products all or -Products current_weather,air_pollution
  [string]$Products = "",
  [string[]]$States = @(),
  [switch]$SkipBudgetCheck
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$functionName = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='PlannerFunctionName'].OutputValue | [0]" `
  --output text

if ($Products -or $States.Count -gt 0 -or $SkipBudgetCheck) {
  $payload = @{}
  if ($Products) { $payload.products = $Products }
  if ($States.Count -gt 0) { $payload.states = @($States | ForEach-Object { $_ -split "," } | Where-Object { $_ }) }
  if ($SkipBudgetCheck) { $payload.skip_budget_check = $true }
  $PayloadFile = ".tool-planner-payload.json"
  # UTF-8 without BOM: Windows PowerShell 5.1 adds a BOM with -Encoding utf8 and Lambda rejects it.
  [System.IO.File]::WriteAllText((Join-Path (Get-Location) $PayloadFile), ($payload | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
}

aws lambda invoke `
  --function-name $functionName `
  --payload fileb://$PayloadFile `
  --region $Region `
  .tool-planner-response.json | Out-Null

Get-Content .tool-planner-response.json
