# AI Ops - Lint Script

param(
    [string]$Path = "src",
    [switch]$Fix,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AI Ops - Linter

Usage: .\scripts\lint.ps1 [-Path <path>] [-Fix] [-Help]

Options:
  -Path    Path to lint (default: 'src')
  -Fix     Auto-fix fixable issues
  -Help    Show this help message

Runs:
  1. ruff check (linting)
  2. ruff format --check (formatting)
  3. mypy (type checking)
"@
    exit 0
}

$ErrorActionPreference = "Continue"
$hasErrors = $false

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Ops - Linter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Ruff lint
Write-Host "[1/3] Running ruff check..." -ForegroundColor Yellow
if ($Fix) {
    ruff check $Path --fix
} else {
    ruff check $Path
}
if ($LASTEXITCODE -ne 0) { $hasErrors = $true }

Write-Host ""

# 2. Ruff format
Write-Host "[2/3] Running ruff format check..." -ForegroundColor Yellow
if ($Fix) {
    ruff format $Path
} else {
    ruff format --check $Path
}
if ($LASTEXITCODE -ne 0) { $hasErrors = $true }

Write-Host ""

# 3. Mypy
Write-Host "[3/3] Running mypy..." -ForegroundColor Yellow
mypy $Path --ignore-missing-imports
if ($LASTEXITCODE -ne 0) { $hasErrors = $true }

Write-Host ""
if ($hasErrors) {
    Write-Host "Lint issues found ✗" -ForegroundColor Red
    Write-Host "Run with -Fix to auto-fix what can be fixed." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "All lint checks passed ✓" -ForegroundColor Green
    exit 0
}
