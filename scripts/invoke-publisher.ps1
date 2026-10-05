param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$functionName = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='PublisherFunctionName'].OutputValue | [0]" `
  --output text

aws lambda invoke `
  --function-name $functionName `
  --payload fileb://events/publisher-event.json `
  --region $Region `
  .tool-publisher-response.json | Out-Null

Get-Content .tool-publisher-response.json
