param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1",
  [string]$PayloadFile = "events/planner-event.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$functionName = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='PlannerFunctionName'].OutputValue | [0]" `
  --output text

aws lambda invoke `
  --function-name $functionName `
  --payload fileb://$PayloadFile `
  --region $Region `
  .tool-planner-response.json

Get-Content .tool-planner-response.json
