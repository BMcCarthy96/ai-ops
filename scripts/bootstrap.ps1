# AI Ops Bootstrap Script
# Sets up the development environment for AI Ops.

param(
    [switch]$SkipVenv,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AI Ops Bootstrap Script

Usage: .\scripts\bootstrap.ps1 [-SkipVenv] [-Help]

Options:
  -SkipVenv    Skip virtual environment creation (use if you manage your own)
  -Help        Show this help message

What this script does:
  1. Checks Python version (requires 3.11+)
  2. Creates a virtual environment (.venv)
  3. Installs project dependencies
  4. Installs dev dependencies
  5. Verifies the installation
"@
    exit 0
}

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Ops - Bootstrap" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python version
Write-Host "[1/5] Checking Python version..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    $versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
    if ($versionMatch) {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Host "ERROR: Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
            exit 1
        }
        Write-Host "  Found: $pythonVersion ✓" -ForegroundColor Green
    }
} catch {
    Write-Host "ERROR: Python not found. Install Python 3.11+ first." -ForegroundColor Red
    exit 1
}

# 2. Create virtual environment
if (-not $SkipVenv) {
    Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Yellow
    if (Test-Path ".venv") {
        Write-Host "  .venv already exists, skipping creation" -ForegroundColor DarkYellow
    } else {
        python -m venv .venv
        Write-Host "  Created .venv ✓" -ForegroundColor Green
    }

    # Activate
    Write-Host "  Activating .venv..." -ForegroundColor Yellow
    & .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "[2/5] Skipping virtual environment (--SkipVenv)" -ForegroundColor DarkYellow
}

# 3. Install dependencies
Write-Host "[3/5] Installing project dependencies..." -ForegroundColor Yellow
pip install -e "." --quiet
Write-Host "  Dependencies installed ✓" -ForegroundColor Green

# 4. Install dev dependencies
Write-Host "[4/5] Installing dev dependencies..." -ForegroundColor Yellow
pip install -e ".[dev]" --quiet
Write-Host "  Dev dependencies installed ✓" -ForegroundColor Green

# 5. Verify installation
Write-Host "[5/5] Verifying installation..." -ForegroundColor Yellow
try {
    python -c "import ai_ops; print(f'  ai_ops version: {ai_ops.__version__}')"
    Write-Host "  Verification passed ✓" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: ai_ops import failed. This is expected if src is empty." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Bootstrap complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  .\scripts\run-tests.ps1   # Run tests"
Write-Host "  .\scripts\lint.ps1        # Run linter"
Write-Host ""
