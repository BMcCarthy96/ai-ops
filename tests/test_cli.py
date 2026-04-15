"""
Tests for the AI Ops CLI — specifically the worktree wiring added in Slice 2.

Tests verify that the CLI passes the correct WorktreeManager configuration to
create_pipeline depending on the --no-persist flag.  The pipeline itself is
mocked so these tests stay fast and free of filesystem/git side-effects.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ and repo root are on the path (mirrors test_pipeline.py setup)
_src_path = str(Path(__file__).resolve().parents[1] / "src")
_repo_root = str(Path(__file__).resolve().parents[1])
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_invoke_result(run_id: str = "test-cli-run") -> dict:
    """Return a minimal pipeline result dict sufficient for cli.main() to print."""
    return {
        "status": "completed",
        "current_stage": "done",
        "run_id": run_id,
        "errors": [],
        "dispatcher_output": {},
        "reviewer_output": {},
        "approval_decisions": [],
        "revision_count": 0,
        "worktree_path": "",
    }


def _run_main(argv: list[str]) -> dict:
    """
    Invoke cli.main() with the given argv and return captured create_pipeline kwargs.

    Patches:
    - sys.argv
    - workflows.langgraph.graphs.dispatch_pipeline.create_pipeline (captures kwargs)
    - The compiled pipeline's invoke() (returns a minimal result)

    Returns the kwargs dict that was passed to create_pipeline.
    """
    captured: dict = {}

    mock_pipeline = MagicMock()
    mock_pipeline.invoke.return_value = _fake_invoke_result(
        run_id=next((argv[i + 1] for i, a in enumerate(argv) if a == "--run-id"), "cli-test")
    )

    def fake_create_pipeline(**kwargs):
        captured.update(kwargs)
        return mock_pipeline

    with patch("sys.argv", ["ai_ops.cli"] + argv):
        with patch(
            "workflows.langgraph.graphs.dispatch_pipeline.create_pipeline",
            fake_create_pipeline,
        ):
            # Force reimport so the patched create_pipeline is picked up on the
            # `from ... import create_pipeline` inside main().
            import importlib
            import ai_ops.cli as cli_module
            importlib.reload(cli_module)
            cli_module.main()

    return captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCLIWorktreeWiring:
    """Tests that verify the CLI correctly wires WorktreeManager into create_pipeline."""

    def test_persist_run_passes_worktree_manager(self, capsys):
        """Default (persisting) run passes a WorktreeManager instance."""
        from ai_ops.runtime.worktree import WorktreeManager

        kwargs = _run_main([
            "--no-interactive",
            "--run-id", "cli-wt-001",
            "Build something",
        ])

        assert "worktree_manager" in kwargs, "worktree_manager not passed to create_pipeline"
        assert isinstance(kwargs["worktree_manager"], WorktreeManager), (
            f"Expected WorktreeManager, got {type(kwargs['worktree_manager'])}"
        )

    def test_no_persist_passes_none_worktree_manager(self, capsys):
        """--no-persist run passes worktree_manager=None."""
        kwargs = _run_main([
            "--no-interactive",
            "--no-persist",
            "--run-id", "cli-wt-002",
            "Build something",
        ])

        assert "worktree_manager" in kwargs, "worktree_manager key missing from create_pipeline kwargs"
        assert kwargs["worktree_manager"] is None, (
            f"Expected None for --no-persist, got {kwargs['worktree_manager']}"
        )

    def test_persist_results_true_when_not_no_persist(self, capsys):
        """persist_results=True is passed when --no-persist is not set."""
        kwargs = _run_main([
            "--no-interactive",
            "--run-id", "cli-wt-003",
            "Build something",
        ])

        assert kwargs.get("persist_results") is True

    def test_persist_results_false_when_no_persist(self, capsys):
        """persist_results=False is passed when --no-persist is set."""
        kwargs = _run_main([
            "--no-interactive",
            "--no-persist",
            "--run-id", "cli-wt-004",
            "Build something",
        ])

        assert kwargs.get("persist_results") is False

    def test_worktree_line_in_output_when_persisting(self, capsys):
        """CLI prints 'Worktree: yes' when persisting."""
        _run_main([
            "--no-interactive",
            "--run-id", "cli-wt-005",
            "Build something",
        ])

        out = capsys.readouterr().out
        assert "Worktree:  yes" in out, f"'Worktree: yes' not found in output:\n{out}"

    def test_worktree_line_in_output_when_no_persist(self, capsys):
        """CLI prints 'Worktree: no' when --no-persist is set."""
        _run_main([
            "--no-interactive",
            "--no-persist",
            "--run-id", "cli-wt-006",
            "Build something",
        ])

        out = capsys.readouterr().out
        assert "Worktree:  no" in out, f"'Worktree: no' not found in output:\n{out}"

    def test_revision_count_shown_when_nonzero(self, capsys):
        """CLI prints revision count when the pipeline performed retries."""
        mock_pipeline = MagicMock()
        mock_pipeline.invoke.return_value = {
            **_fake_invoke_result("cli-rev-001"),
            "reviewer_output": {"verdict": "PASS"},
            "revision_count": 1,
        }

        with patch("sys.argv", ["ai_ops.cli", "--no-interactive", "--no-persist",
                                "--run-id", "cli-rev-001", "Build"]):
            with patch(
                "workflows.langgraph.graphs.dispatch_pipeline.create_pipeline",
                lambda **kw: mock_pipeline,
            ):
                import importlib
                import ai_ops.cli as cli_module
                importlib.reload(cli_module)
                cli_module.main()

        out = capsys.readouterr().out
        assert "Revisions: 1" in out, f"Revision count not printed:\n{out}"

    def test_revision_count_not_shown_when_zero(self, capsys):
        """CLI does not print revision count when revision_count is 0."""
        mock_pipeline = MagicMock()
        mock_pipeline.invoke.return_value = {
            **_fake_invoke_result("cli-rev-002"),
            "reviewer_output": {"verdict": "PASS"},
            "revision_count": 0,
        }

        with patch("sys.argv", ["ai_ops.cli", "--no-interactive", "--no-persist",
                                "--run-id", "cli-rev-002", "Build"]):
            with patch(
                "workflows.langgraph.graphs.dispatch_pipeline.create_pipeline",
                lambda **kw: mock_pipeline,
            ):
                import importlib
                import ai_ops.cli as cli_module
                importlib.reload(cli_module)
                cli_module.main()

        out = capsys.readouterr().out
        assert "Revisions" not in out, f"Revision count printed when it should be hidden:\n{out}"
