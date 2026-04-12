"""
Tests for the run persistence system.

Verifies file-based persistence of agent outputs, run summaries,
artifact indexes, and run finalization.
"""

import yaml
import pytest
from pathlib import Path

from ai_ops.runtime.persistence import RunPersistence


@pytest.fixture
def persistence(tmp_path):
    """Create a RunPersistence with a temp directory as repo root."""
    repo_root = tmp_path / "ai-ops"
    # Create the directory structure
    (repo_root / "runs" / "active").mkdir(parents=True)
    (repo_root / "runs" / "completed").mkdir(parents=True)
    (repo_root / "runs" / "failed").mkdir(parents=True)
    (repo_root / "memory" / "run-summaries").mkdir(parents=True)
    return RunPersistence(repo_root=repo_root)


class TestRunDirectory:
    """Test run directory creation."""

    def test_create_run_dir(self, persistence):
        path = persistence.create_run_dir("test-run-001")
        assert path.exists()
        assert path.is_dir()
        assert "test-run-001" in str(path)

    def test_create_run_dir_idempotent(self, persistence):
        path1 = persistence.create_run_dir("test-run-002")
        path2 = persistence.create_run_dir("test-run-002")
        assert path1 == path2


class TestAgentOutputPersistence:
    """Test saving agent outputs."""

    def test_save_agent_output(self, persistence):
        output = {
            "status": "completed",
            "result": {"classification": {"task_type": "build"}},
        }
        path = persistence.save_agent_output("test-run-003", "dispatcher", output)
        assert path.exists()
        assert path.name == "dispatcher-output.yaml"

        # Verify YAML content
        data = yaml.safe_load(path.read_text())
        assert data["agent"] == "dispatcher"
        assert data["run_id"] == "test-run-003"
        assert data["output"]["status"] == "completed"

    def test_save_multiple_agents(self, persistence):
        for agent in ["dispatcher", "research", "builder", "reviewer"]:
            path = persistence.save_agent_output(
                "test-run-004", agent, {"status": "completed"}
            )
            assert path.exists()

        # All four output files should exist
        run_dir = persistence.runs_dir / "active" / "test-run-004"
        files = list(run_dir.glob("*-output.yaml"))
        assert len(files) == 4


class TestRunSummary:
    """Test run summary persistence."""

    def test_save_run_summary(self, persistence):
        state = {
            "run_id": "test-run-005",
            "task_description": "Build auth module",
            "status": "completed",
            "approval_level": 0,
            "dispatcher_output": {
                "classification": {
                    "task_type": "build",
                    "complexity": "moderate",
                    "required_agents": ["research", "builder", "reviewer"],
                },
            },
            "reviewer_output": {
                "verdict": "PASS",
            },
            "errors": [],
            "escalations": [],
        }
        path = persistence.save_run_summary("test-run-005", state)
        assert path.exists()
        assert path.name == "test-run-005.yaml"

        data = yaml.safe_load(path.read_text())
        assert data["run_id"] == "test-run-005"
        assert data["status"] == "completed"
        assert data["task_type"] == "build"
        assert data["reviewer_verdict"] == "PASS"
        assert data["agents_used"] == ["research", "builder", "reviewer"]


class TestArtifactIndex:
    """Test artifact index persistence."""

    def test_save_artifact_index(self, persistence):
        artifacts = [
            {"name": "dispatcher-output.yaml", "type": "agent_output", "agent": "dispatcher"},
            {"name": "research-output.yaml", "type": "agent_output", "agent": "research"},
        ]
        path = persistence.save_artifact_index("test-run-006", artifacts)
        assert path.exists()
        assert path.name == "artifact-index.yaml"

        data = yaml.safe_load(path.read_text())
        assert data["run_id"] == "test-run-006"
        assert len(data["artifacts"]) == 2


class TestRunFinalization:
    """Test moving runs from active to completed/failed."""

    def test_finalize_completed(self, persistence):
        # Create an active run
        persistence.create_run_dir("test-run-007")
        persistence.save_agent_output("test-run-007", "dispatcher", {"status": "done"})

        # Finalize
        dest = persistence.finalize_run("test-run-007", "completed")
        assert dest.exists()
        assert "completed" in str(dest)
        assert not (persistence.runs_dir / "active" / "test-run-007").exists()

        # Agent output should be in completed dir
        assert (dest / "dispatcher-output.yaml").exists()

    def test_finalize_failed(self, persistence):
        persistence.create_run_dir("test-run-008")
        dest = persistence.finalize_run("test-run-008", "failed")
        assert "failed" in str(dest)

    def test_finalize_nonexistent(self, persistence):
        """Finalizing a non-existent run should not crash."""
        dest = persistence.finalize_run("nonexistent", "completed")
        # Should return the would-be path without error
        assert "completed" in str(dest)
