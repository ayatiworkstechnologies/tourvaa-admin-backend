$ErrorActionPreference = "Stop"

$backend = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $backend
$runner = Join-Path $root "scripts\check-both.ps1"

& powershell -ExecutionPolicy Bypass -File $runner
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
