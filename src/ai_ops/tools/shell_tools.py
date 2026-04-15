"""
ShellTools — shell command execution for agent worktree operations.

Provides scoped command execution and tool-specific helpers (ruff, mypy,
pytest) for the Reviewer agent. All commands run with the worktree as cwd.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ShellResult:
    """Result of a shell command execution."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        """True if the command exited with code 0."""
        return self.returncode == 0

    @property
    def status(self) -> str:
        """'PASS' if returncode is 0, 'FAIL' otherwise."""
        return "PASS" if self.passed else "FAIL"


class ShellTools:
    """
    Shell command runner scoped to a worktree directory.

    All commands execute with cwd set to the worktree path.
    Uses the current Python interpreter (sys.executable) for
    ruff, mypy, and pytest to ensure consistent environment.
    """

    def __init__(self, worktree_path: Path) -> None:
        self.worktree_path = worktree_path

    def run_command(self, cmd: list[str], timeout: int = 60) -> ShellResult:
        """
        Run a shell command in the worktree directory.

        Args:
            cmd: Command and arguments as a list of strings.
            timeout: Maximum seconds to wait (default: 60).

        Returns:
            ShellResult with returncode, stdout, stderr.
        """
        logger.info("Running command in %s: %s", self.worktree_path, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                cwd=self.worktree_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ShellResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out after %ds: %s", timeout, cmd)
            return ShellResult(returncode=1, stdout="", stderr=f"Command timed out after {timeout}s")
        except Exception as exc:
            logger.warning("Command failed to execute: %s — %s", cmd, exc)
            return ShellResult(returncode=1, stdout="", stderr=str(exc))

    def run_ruff(self, paths: list[str] | None = None) -> ShellResult:
        """
        Run ruff lint check on the worktree or specified paths.

        Args:
            paths: Specific paths to check. Defaults to worktree root (".").

        Returns:
            ShellResult from ruff check.
        """
        targets = paths or ["."]
        return self.run_command([sys.executable, "-m", "ruff", "check"] + targets)

    def run_mypy(self, paths: list[str] | None = None) -> ShellResult:
        """
        Run mypy type check on the worktree or specified paths.

        Args:
            paths: Specific paths to check. Defaults to worktree root (".").

        Returns:
            ShellResult from mypy.
        """
        targets = paths or ["."]
        return self.run_command([sys.executable, "-m", "mypy"] + targets)

    def run_pytest(self, paths: list[str] | None = None) -> ShellResult:
        """
        Run pytest on the worktree or specified paths.

        Args:
            paths: Specific test paths. Defaults to worktree root (".").

        Returns:
            ShellResult from pytest.
        """
        targets = paths or ["."]
        return self.run_command([sys.executable, "-m", "pytest"] + targets)
