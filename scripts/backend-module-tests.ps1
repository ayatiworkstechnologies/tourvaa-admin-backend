param(
  [string[]]$Module = @(),
  [switch]$Write,
  [string]$BaseUrl = "http://127.0.0.1:8000/api",
  [string]$Email = "admin@tourvaa.com",
  [string]$Password = "Admin@123"
)

$ErrorActionPreference = "Stop"

$backend = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $backend
$runner = Join-Path $root "scripts\backend-module-tests.ps1"

$argsList = @("-ExecutionPolicy", "Bypass", "-File", $runner, "-BaseUrl", $BaseUrl, "-Email", $Email, "-Password", $Password)
if ($Module.Count -gt 0) {
  $argsList += "-Module"
  $argsList += $Module
}
if ($Write.IsPresent) {
  $argsList += "-Write"
}

& powershell @argsList
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
