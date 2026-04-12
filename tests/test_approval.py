"""
Tests for the approval handling system.

Verifies that approval levels are enforced correctly at runtime.
"""

from ai_ops.runtime.approval import (
    ApprovalResult,
    AutoApprovalHandler,
    InteractiveApprovalHandler,
)


class TestAutoApprovalHandler:
    """Test the non-interactive approval handler."""

    def test_level_0_approved(self):
        handler = AutoApprovalHandler()
        result = handler.check(0, "Read a file")
        assert result == ApprovalResult.APPROVED

    def test_level_1_approved(self):
        handler = AutoApprovalHandler()
        result = handler.check(1, "Write code in worktree")
        assert result == ApprovalResult.APPROVED

    def test_level_2_denied(self):
        """Level 2 should be denied (no human to approve)."""
        handler = AutoApprovalHandler()
        result = handler.check(2, "Merge to main")
        assert result == ApprovalResult.DENIED

    def test_level_3_blocked(self):
        """Level 3 should always be blocked."""
        handler = AutoApprovalHandler()
        result = handler.check(3, "Delete production data")
        assert result == ApprovalResult.BLOCKED

    def test_custom_max_level(self):
        """Custom max_auto_level should change what gets auto-approved."""
        handler = AutoApprovalHandler(max_auto_level=0)
        assert handler.check(0, "Read") == ApprovalResult.APPROVED
        assert handler.check(1, "Write") == ApprovalResult.DENIED

    def test_max_level_2(self):
        """max_auto_level=2 should approve everything except level 3."""
        handler = AutoApprovalHandler(max_auto_level=2)
        assert handler.check(0, "Read") == ApprovalResult.APPROVED
        assert handler.check(1, "Write") == ApprovalResult.APPROVED
        assert handler.check(2, "Deploy") == ApprovalResult.APPROVED
        assert handler.check(3, "Delete") == ApprovalResult.BLOCKED


class TestInteractiveApprovalHandler:
    """Test the interactive approval handler (limited — cannot test stdin)."""

    def test_level_0_auto_approved(self):
        """Level 0 should auto-approve without any interaction."""
        handler = InteractiveApprovalHandler()
        result = handler.check(0, "Read a file")
        assert result == ApprovalResult.APPROVED

    def test_level_1_auto_approved(self):
        """Level 1 should auto-approve (with notice)."""
        handler = InteractiveApprovalHandler()
        result = handler.check(1, "Write in worktree")
        assert result == ApprovalResult.APPROVED

    def test_level_3_blocked(self):
        """Level 3 should always be blocked."""
        handler = InteractiveApprovalHandler()
        result = handler.check(3, "Delete production data")
        assert result == ApprovalResult.BLOCKED

    def test_level_2_eof_denied(self, monkeypatch):
        """Level 2 with EOF input should deny."""
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError))
        handler = InteractiveApprovalHandler()
        result = handler.check(2, "Merge to main")
        assert result == ApprovalResult.DENIED

    def test_level_2_yes_approved(self, monkeypatch):
        """Level 2 with 'y' input should approve."""
        monkeypatch.setattr("builtins.input", lambda _: "y")
        handler = InteractiveApprovalHandler()
        result = handler.check(2, "Deploy staging")
        assert result == ApprovalResult.APPROVED

    def test_level_2_no_denied(self, monkeypatch):
        """Level 2 with 'n' input should deny."""
        monkeypatch.setattr("builtins.input", lambda _: "n")
        handler = InteractiveApprovalHandler()
        result = handler.check(2, "Deploy staging")
        assert result == ApprovalResult.DENIED


class TestApprovalResult:
    """Test ApprovalResult enum values."""

    def test_values(self):
        assert ApprovalResult.APPROVED.value == "approved"
        assert ApprovalResult.DENIED.value == "denied"
        assert ApprovalResult.BLOCKED.value == "blocked"
