param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-StackOutput([string]$Key) {
  $value = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" `
    --output text
  if ($value -eq "None") { return "" }
  return $value
}

$bucket = Get-StackOutput "SiteBucketName"
if (-not $bucket) { throw "SiteBucketName output not found in stack $StackName." }

# data/ is owned by the Curator and the Publisher; never upload or delete it from here.
aws s3 sync frontend/ "s3://$bucket/" --delete --exclude "data/*" --cache-control "public, max-age=300" --region $Region
if ($LASTEXITCODE -ne 0) { throw "aws s3 sync failed" }
aws s3 cp frontend/index.html "s3://$bucket/index.html" --cache-control "no-cache" --content-type "text/html; charset=utf-8" --region $Region
if ($LASTEXITCODE -ne 0) { throw "aws s3 cp failed" }

$distribution = Get-StackOutput "SiteDistributionId"
if ($distribution) {
  aws cloudfront create-invalidation --distribution-id $distribution --paths "/index.html" "/assets/*" "/favicon.svg" --query "Invalidation.Id" --output text | Out-Null
  Write-Host "Dashboard: $(Get-StackOutput 'DashboardUrl')"
} else {
  Write-Host "Frontend uploaded to s3://$bucket (EnableFrontend=false, no CloudFront distribution)."
}
