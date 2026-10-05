param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $SkipInstall) {
  python -m pip install -r requirements.txt
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

python -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cfn-lint template.yaml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Get-Command node -ErrorAction SilentlyContinue) {
  Get-ChildItem frontend/assets/*.js | ForEach-Object {
    Get-Content -Raw -LiteralPath $_.FullName | node --input-type=module --check
    if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax error in $($_.Name)" }
  }
}
