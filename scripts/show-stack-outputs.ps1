param(
  [string]$StackName = "weather-data-pipeline-dev",
  [string]$Region = "sa-east-1"
)

$ErrorActionPreference = "Stop"

aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $Region `
  --query "Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}" `
  --output table
