param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1",
  [string]$TargetHour = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$functionName = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $Region `
  --query "Stacks[0].Outputs[?OutputKey=='CuratorFunctionName'].OutputValue | [0]" `
  --output text

$payload = "{}"
if ($TargetHour) {
  $payload = "{`"target_hour`": `"$TargetHour`"}"
}

$payloadPath = ".tool-curator-payload.json"
$responsePath = ".tool-curator-response.json"
Set-Content -LiteralPath $payloadPath -Value $payload -Encoding utf8

aws lambda invoke `
  --function-name $functionName `
  --payload fileb://$payloadPath `
  --region $Region `
  $responsePath

Get-Content $responsePath
