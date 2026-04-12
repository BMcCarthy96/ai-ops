# AI Ops - Create Worktree Script
# Creates an isolated git worktree for agent work.

param(
    [Parameter(Mandatory=$true)]
    [string]$RunId,

    [Parameter(Mandatory=$true)]
    [ValidateSet("dispatcher", "research", "builder", "reviewer")]
    [string]$Agent,

    [string]$Description = "work",
    [switch]$Help
)

if ($Help) {
    Write-Host @"
AI Ops - Create Worktree

Usage: .\scripts\create-worktree.ps1 -RunId <run-id> -Agent <agent> [-Description <desc>]

Parameters:
  -RunId        The run ID (e.g., '2026-04-12-scaffold-auth')
  -Agent        The agent creating the worktree (dispatcher, research, builder, reviewer)
  -Description  Short description of the work (default: 'work')

Creates:
  - A new git branch: ai-ops/{agent}/{run-id}/{description}
  - A new worktree at: ../worktrees/{run-id}/
"@
    exit 0
}

$ErrorActionPreference = "Stop"

# Validate git repo
if (-not (Test-Path ".git")) {
    Write-Host "ERROR: Not a git repository. Run from the ai-ops root." -ForegroundColor Red
    exit 1
}

$branchName = "ai-ops/$Agent/$RunId/$Description"
$worktreePath = "../worktrees/$RunId"

Write-Host "Creating worktree..." -ForegroundColor Cyan
Write-Host "  Branch:   $branchName" -ForegroundColor Yellow
Write-Host "  Path:     $worktreePath" -ForegroundColor Yellow

# Check if worktree already exists
if (Test-Path $worktreePath) {
    Write-Host "ERROR: Worktree already exists at $worktreePath" -ForegroundColor Red
    exit 1
}

# Create the worktree
try {
    git worktree add -b $branchName $worktreePath
    Write-Host ""
    Write-Host "Worktree created successfully ✓" -ForegroundColor Green
    Write-Host ""
    Write-Host "To work in the worktree:" -ForegroundColor Yellow
    Write-Host "  cd $worktreePath"
    Write-Host ""
    Write-Host "To remove the worktree when done:" -ForegroundColor Yellow
    Write-Host "  git worktree remove $worktreePath"
    Write-Host "  git branch -d $branchName"
} catch {
    Write-Host "ERROR: Failed to create worktree: $_" -ForegroundColor Red
    exit 1
}
