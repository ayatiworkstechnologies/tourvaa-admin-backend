<#
  Clears only reproducible local development artifacts for both Tourvaa repos.

  Safe to schedule daily. It deliberately does not touch .env files, databases,
  uploads, backups, virtual environments, node_modules, Redis, or .next (which
  may be in use by `next dev`).
#>

$ErrorActionPreference = "Stop"

$backendRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $backendRoot
$frontendRoot = Join-Path $workspaceRoot "tourvaa-admin-frontend"

function Remove-GeneratedItem {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($workspaceRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the Tourvaa workspace: $resolved"
    }

    try {
        Remove-Item -LiteralPath $resolved -Recurse -Force
        Write-Output "Removed $resolved"
    } catch {
        # A cache owned by another Windows account is harmless; report it and
        # continue so one stale test cache never prevents the remaining cleanup.
        Write-Warning "Could not remove ${resolved}: $($_.Exception.Message)"
    }
}

$targets = @(
    (Join-Path $backendRoot ".pytest_cache"),
    (Join-Path $backendRoot "__pycache__"),
    (Join-Path $frontendRoot "test-results"),
    (Join-Path $frontendRoot "coverage"),
    (Join-Path $frontendRoot "playwright-report"),
    (Join-Path $frontendRoot "tsconfig.tsbuildinfo")
)

# Restrict the recursive lookup to application-owned folders: never scan or
# remove bytecode below the virtual environment.
foreach ($sourceRoot in @(
    (Join-Path $backendRoot "app"),
    (Join-Path $backendRoot "alembic"),
    (Join-Path $backendRoot "scripts"),
    (Join-Path $backendRoot "tests")
)) {
    if (Test-Path -LiteralPath $sourceRoot) {
        $targets += Get-ChildItem -LiteralPath $sourceRoot -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName }
    }
}

$targets | Select-Object -Unique | ForEach-Object { Remove-GeneratedItem -Path $_ }
Write-Output "Tourvaa generated-cache cleanup completed at $(Get-Date -Format o)."
