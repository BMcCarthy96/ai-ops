# AI Ops - Run Tests Script

param(
    [string]$Path = "tests",
    [switch]$Verbose,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AI Ops - Run Tests

Usage: .\scripts\run-tests.ps1 [-Path <path>] [-Verbose] [-Help]

Options:
  -Path      Test path to run (default: 'tests')
  -Verbose   Show verbose test output
  -Help      Show this help message
"@
    exit 0
}

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Ops - Test Runner" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if pytest is available
try {
    python -m pytest --version 2>&1 | Out-Null
} catch {
    Write-Host "ERROR: pytest not found. Run .\scripts\bootstrap.ps1 first." -ForegroundColor Red
    exit 1
}

# Build pytest args
$pytestArgs = @($Path, "--tb=short")
if ($Verbose) {
    $pytestArgs += "-v"
}

Write-Host "Running: python -m pytest $($pytestArgs -join ' ')" -ForegroundColor Yellow
Write-Host ""

python -m pytest @pytestArgs

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "All tests passed ✓" -ForegroundColor Green
} elseif ($exitCode -eq 5) {
    Write-Host "No tests found. This is expected in Phase 1." -ForegroundColor DarkYellow
} else {
    Write-Host "Tests failed ✗" -ForegroundColor Red
}

exit $exitCode
