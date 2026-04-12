"""
Approval handling for AI Ops.

Enforces the approval matrix at runtime. Each action has a level (0-3)
and the handler decides whether to proceed, pause, or block.

Levels:
    0 (AUTO)    — Proceed immediately, no interaction.
    1 (SOFT)    — Proceed but log a notice.
    2 (HARD)    — Pause and require explicit human approval.
    3 (BLOCKED) — Halt immediately. Cannot be overridden at runtime.
"""

from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ApprovalResult(str, Enum):
    """Result of an approval check."""
    APPROVED = "approved"
    DENIED = "denied"
    BLOCKED = "blocked"


@runtime_checkable
class ApprovalHandler(Protocol):
    """Protocol for approval handlers. Swap implementations for different contexts."""

    def check(self, level: int, description: str) -> ApprovalResult:
        """
        Check whether an action at the given approval level should proceed.

        Args:
            level: Approval level (0-3).
            description: Human-readable description of the action.

        Returns:
            ApprovalResult indicating whether to proceed.
        """
        ...


class InteractiveApprovalHandler:
    """
    Approval handler for interactive CLI use.

    Level 0: auto-approve, silent.
    Level 1: auto-approve, print notice.
    Level 2: prompt stdin for explicit y/n.
    Level 3: block, no override.
    """

    def check(self, level: int, description: str) -> ApprovalResult:
        if level <= 0:
            logger.debug("Level 0 (auto): %s", description)
            return ApprovalResult.APPROVED

        if level == 1:
            print(f"[APPROVAL L1 — NOTICE] {description}")
            logger.info("Level 1 (soft): %s — auto-approved", description)
            return ApprovalResult.APPROVED

        if level == 2:
            print(f"\n[APPROVAL L2 — REQUIRED] {description}")
            try:
                response = input("Approve? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nApproval denied (no input).")
                return ApprovalResult.DENIED

            if response in ("y", "yes"):
                logger.info("Level 2 (hard): %s — approved by operator", description)
                return ApprovalResult.APPROVED
            else:
                logger.info("Level 2 (hard): %s — denied by operator", description)
                return ApprovalResult.DENIED

        # Level 3+
        print(f"[APPROVAL L3 — BLOCKED] {description}", file=sys.stderr)
        logger.warning("Level 3 (blocked): %s — action forbidden", description)
        return ApprovalResult.BLOCKED


class AutoApprovalHandler:
    """
    Non-interactive approval handler for tests and CI.

    Level 0-1: auto-approve.
    Level 2-3: deny/block (no human to ask).
    """

    def __init__(self, max_auto_level: int = 1) -> None:
        """
        Args:
            max_auto_level: Maximum level to auto-approve.
                            Default 1 = approve Level 0 and 1, deny Level 2+.
        """
        self._max_auto_level = max_auto_level

    def check(self, level: int, description: str) -> ApprovalResult:
        if level <= self._max_auto_level:
            logger.debug("AutoApproval: level %d approved — %s", level, description)
            return ApprovalResult.APPROVED

        if level >= 3:
            logger.warning("AutoApproval: level %d blocked — %s", level, description)
            return ApprovalResult.BLOCKED

        logger.info("AutoApproval: level %d denied (no human) — %s", level, description)
        return ApprovalResult.DENIED
