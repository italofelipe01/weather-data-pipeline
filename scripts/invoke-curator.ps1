param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1",
  # One hour to (re)build, e.g. "2026-06-25T12:00:00Z".
  [string]$TargetHour = "",
  # Backfill a range of hours (raw data is kept for RawDataRetentionDays).
  [string]$StartHour = "",
  [string]$EndHour = "",
  # Default run: only hours missing in the last N hours.
  [int]$LookbackHours = 0,
  # Rewrite the dashboard daily series from all curated daily files.
  [switch]$RebuildServing
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$functionName = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='CuratorFunctionName'].OutputValue | [0]" `
  --output text

$payload = @{}
if ($TargetHour) { $payload.target_hour = $TargetHour }
if ($StartHour) { $payload.start_hour = $StartHour }
if ($EndHour) { $payload.end_hour = $EndHour }
if ($LookbackHours -gt 0) { $payload.lookback_hours = $LookbackHours }
if ($RebuildServing) { $payload.rebuild_serving = $true }

$payloadPath = ".tool-curator-payload.json"
$responsePath = ".tool-curator-response.json"
# UTF-8 without BOM: Windows PowerShell 5.1 adds a BOM with -Encoding utf8 and Lambda rejects it.
[System.IO.File]::WriteAllText((Join-Path (Get-Location) $payloadPath), ($payload | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))

aws lambda invoke `
  --function-name $functionName `
  --payload fileb://$payloadPath `
  --cli-read-timeout 320 `
  --region $Region `
  $responsePath | Out-Null

Get-Content $responsePath
