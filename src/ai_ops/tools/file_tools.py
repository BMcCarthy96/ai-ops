"""
FileTools — file I/O utilities for agent worktree operations.

Provides safe, worktree-scoped file operations for the Builder agent.
All paths are resolved relative to the worktree root and validated to
prevent writes outside the worktree boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FileTools:
    """
    File I/O scoped to a specific worktree directory.

    All operations are confined to the worktree path. Attempts to read
    or write outside the worktree boundary raise ValueError.
    """

    def __init__(self, worktree_path: Path) -> None:
        self.worktree_path = worktree_path.resolve()

    def _safe_path(self, relative_path: str) -> Path:
        """
        Resolve a relative path within the worktree.

        Raises:
            ValueError: If the resolved path escapes the worktree root
                        (path traversal attempt).
        """
        resolved = (self.worktree_path / relative_path).resolve()
        if not resolved.is_relative_to(self.worktree_path):
            raise ValueError(
                f"Path {relative_path!r} resolves outside worktree "
                f"({self.worktree_path}): {resolved}"
            )
        return resolved

    def write_file(self, relative_path: str, content: str) -> Path:
        """
        Write a file to the worktree.

        Creates intermediate directories as needed.

        Args:
            relative_path: Path relative to the worktree root.
            content: File content as a string.

        Returns:
            Absolute path of the written file.

        Raises:
            ValueError: If relative_path escapes the worktree root.
        """
        path = self._safe_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote %s (%d bytes)", path, len(content))
        return path

    def read_file(self, relative_path: str) -> str:
        """
        Read a file from the worktree.

        Args:
            relative_path: Path relative to the worktree root.

        Returns:
            File content as a string.

        Raises:
            ValueError: If relative_path escapes the worktree root.
            FileNotFoundError: If the file does not exist.
        """
        path = self._safe_path(relative_path)
        return path.read_text(encoding="utf-8")

    def list_files(self, directory: str = ".", pattern: str = "**/*") -> list[str]:
        """
        List files in the worktree matching a glob pattern.

        Args:
            directory: Directory relative to the worktree root to search in.
            pattern: Glob pattern (default: all files recursively).

        Returns:
            List of relative path strings, sorted.

        Raises:
            ValueError: If directory escapes the worktree root.
        """
        base = self._safe_path(directory)
        if not base.exists():
            return []
        return sorted(
            str(p.relative_to(self.worktree_path))
            for p in base.glob(pattern)
            if p.is_file()
        )
