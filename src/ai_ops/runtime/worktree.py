"""
WorktreeManager — git worktree lifecycle for AI Ops runs.

Creates and destroys isolated git worktrees for agent work.
Each run gets its own branch and worktree directory, following the
convention established in scripts/create-worktree.ps1.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve the repo root relative to this file's location (src/ai_ops/runtime/)
_REPO_ROOT = Path(__file__).resolve().parents[3]


class WorktreeManager:
    """
    Manages git worktrees for pipeline runs.

    Each run gets:
    - A branch:   ai-ops/run/{run_id}
    - A worktree: {repo_root}/../worktrees/{run_id}/

    Both are cleaned up when destroy() is called.
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or _REPO_ROOT

    def path(self, run_id: str) -> Path:
        """Return the worktree path for a run (does not create it)."""
        return self.repo_root.parent / "worktrees" / run_id

    def branch_name(self, run_id: str) -> str:
        """Return the git branch name for a run."""
        return f"ai-ops/run/{run_id}"

    def create(self, run_id: str) -> Path:
        """
        Create a git worktree for the run.

        Creates a new branch and worktree directory. If a stale worktree
        from a previous failed run exists at the same path, it is removed first.

        Returns:
            Path to the created worktree directory.

        Raises:
            RuntimeError: If git worktree add fails.
        """
        path = self.path(run_id)
        branch = self.branch_name(run_id)

        if path.exists():
            logger.warning(
                "Stale worktree found at %s — removing before recreating", path
            )
            self.destroy(run_id)

        path.parent.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(path)],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed for run {run_id!r}: {result.stderr.strip()}"
            )

        logger.info("Created worktree at %s (branch %s)", path, branch)
        return path

    def destroy(self, run_id: str) -> None:
        """
        Remove the worktree and delete its branch.

        Safe to call when the worktree does not exist — logs warnings for
        failures but does not raise so that persist_node cleanup is always
        attempted even after a partial run.
        """
        path = self.path(run_id)
        branch = self.branch_name(run_id)

        # Remove the worktree directory (--force handles untracked/modified files)
        remove_result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if remove_result.returncode != 0:
            logger.warning(
                "git worktree remove failed for %s: %s",
                path,
                remove_result.stderr.strip(),
            )

        # Delete the branch (-D handles branches with no commits or unmerged work)
        branch_result = subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if branch_result.returncode != 0:
            logger.warning(
                "git branch -D failed for %s: %s",
                branch,
                branch_result.stderr.strip(),
            )

        logger.info("Destroyed worktree for run %s", run_id)
