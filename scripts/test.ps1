param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $SkipInstall) {
  python -m pip install -r requirements.txt
}

python -m ruff check .
python -m ruff format --check .
python -m pytest
