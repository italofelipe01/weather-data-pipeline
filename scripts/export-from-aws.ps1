param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1",
  [string]$DataDir = ".local-data",
  # Also copy raw snapshots (kept only RawDataRetentionDays in the cloud); curated tables are always copied.
  [switch]$IncludeRaw
)

# Copies everything the cloud stack produced into the offline layout, so the offline service, the local
# dashboard and scripts/query_local.py keep working after the AWS account is closed. Safe to run often:
# aws s3 sync only downloads new or changed files.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-StackOutput([string]$Key) {
  $value = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" `
    --output text
  if ($LASTEXITCODE -ne 0 -or $value -eq "None") { return "" }
  return $value
}

$rawBucket = Get-StackOutput "RawDataBucketName"
$siteBucket = Get-StackOutput "SiteBucketName"
if (-not $rawBucket) { throw "RawDataBucketName output not found in stack $StackName ($Region)." }

$lake = Join-Path $DataDir "lake"
aws s3 sync "s3://$rawBucket/curated/" (Join-Path $lake "curated") --region $Region --only-show-errors
if ($LASTEXITCODE -ne 0) { throw "failed to copy curated tables" }
if ($IncludeRaw) {
  aws s3 sync "s3://$rawBucket/raw/" (Join-Path $lake "raw") --region $Region --only-show-errors
  if ($LASTEXITCODE -ne 0) { throw "failed to copy raw snapshots" }
}
if ($siteBucket) {
  aws s3 sync "s3://$siteBucket/data/" "frontend/data" --region $Region --only-show-errors
  if ($LASTEXITCODE -ne 0) { throw "failed to copy dashboard data" }
}

$files = (Get-ChildItem -Recurse -File (Join-Path $lake "curated") -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "Exported $files curated files to $lake (dashboard data in frontend/data)."
Write-Host "Next: ./scripts/start-offline.ps1 to keep collecting locally, or python scripts/query_local.py queries/monthly_from_daily.sql"
