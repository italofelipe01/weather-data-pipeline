param(
  [string[]]$States = @(),
  [string]$Products = "all",
  [switch]$SkipFetch,
  [switch]$Serve,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

$argsList = @("scripts/local_pipeline.py", "--products", $Products)
if ($States.Count -gt 0) { $argsList += @("--states", ($States -join ",")) }
if ($SkipFetch) { $argsList += "--skip-fetch" }

& $python @argsList
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Serve) {
  Write-Host "Dashboard em http://localhost:$Port/ (Ctrl+C para parar)"
  & $python -m http.server $Port --directory frontend
}
