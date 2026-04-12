"""
Run persistence for AI Ops.

Handles writing run results to disk:
- Agent outputs as YAML to run directories
- Run summaries to memory/run-summaries/
- Artifact index records
- Moving completed/failed runs from active/ to their final location
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Resolve the repo root (ai-ops/) relative to this file's location
_REPO_ROOT = Path(__file__).resolve().parents[3]

RUNS_DIR = _REPO_ROOT / "runs"
MEMORY_DIR = _REPO_ROOT / "memory"


class RunPersistence:
    """
    File-based persistence for run results.

    All data is written as YAML (structured) or Markdown (human-readable)
    to the repository's runs/ and memory/ directories.
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or _REPO_ROOT
        self.runs_dir = self.repo_root / "runs"
        self.memory_dir = self.repo_root / "memory"

    def create_run_dir(self, run_id: str) -> Path:
        """Create and return the active run directory."""
        run_dir = self.runs_dir / "active" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created run directory: %s", run_dir)
        return run_dir

    def save_agent_output(
        self,
        run_id: str,
        agent_role: str,
        output: dict[str, Any],
    ) -> Path:
        """
        Save an agent's output to the run directory as YAML.

        Args:
            run_id: The run identifier.
            agent_role: The agent role (e.g., "dispatcher").
            output: The agent output dict to persist.

        Returns:
            Path to the written file.
        """
        run_dir = self.runs_dir / "active" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        output_file = run_dir / f"{agent_role}-output.yaml"
        data = {
            "agent": agent_role,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output": output,
        }
        output_file.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("Saved %s output to %s", agent_role, output_file)
        return output_file

    def save_run_summary(self, run_id: str, state: dict[str, Any]) -> Path:
        """
        Write a run summary to memory/run-summaries/.

        Args:
            run_id: The run identifier.
            state: The final pipeline state dict.

        Returns:
            Path to the written summary file.
        """
        summaries_dir = self.memory_dir / "run-summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)

        # Extract key data from state
        dispatcher_out = state.get("dispatcher_output", {})
        reviewer_out = state.get("reviewer_output", {})
        classification = dispatcher_out.get("classification", {})

        summary = {
            "run_id": run_id,
            "date_start": state.get("started_at", datetime.now(timezone.utc).isoformat()),
            "date_end": datetime.now(timezone.utc).isoformat(),
            "status": state.get("status", "unknown"),
            "task_description": state.get("task_description", ""),
            "task_type": classification.get("task_type", "unknown"),
            "complexity": classification.get("complexity", "unknown"),
            "agents_used": classification.get("required_agents", []),
            "approval_level": state.get("approval_level", 0),
            "reviewer_verdict": reviewer_out.get("verdict", "none"),
            "errors": state.get("errors", []),
            "escalations": state.get("escalations", []),
        }

        summary_file = summaries_dir / f"{run_id}.yaml"
        summary_file.write_text(
            yaml.dump(summary, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("Saved run summary to %s", summary_file)
        return summary_file

    def save_artifact_index(self, run_id: str, artifacts: list[dict[str, str]]) -> Path:
        """
        Write an artifact index to the run directory.

        Each artifact entry has: name, type, path, agent.

        Args:
            run_id: The run identifier.
            artifacts: List of artifact dicts.

        Returns:
            Path to the written index file.
        """
        run_dir = self.runs_dir / "active" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        index = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts,
        }

        index_file = run_dir / "artifact-index.yaml"
        index_file.write_text(
            yaml.dump(index, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("Saved artifact index to %s", index_file)
        return index_file

    def finalize_run(self, run_id: str, status: str) -> Path:
        """
        Move a run from active/ to completed/ or failed/.

        Args:
            run_id: The run identifier.
            status: "completed" or "failed".

        Returns:
            Path to the final run directory.
        """
        source = self.runs_dir / "active" / run_id
        dest_parent = self.runs_dir / ("completed" if status == "completed" else "failed")
        dest = dest_parent / run_id

        if not source.exists():
            logger.warning("Run directory not found for finalization: %s", source)
            return dest

        dest_parent.mkdir(parents=True, exist_ok=True)

        # If destination already exists, remove it first
        if dest.exists():
            shutil.rmtree(dest)

        shutil.move(str(source), str(dest))
        logger.info("Finalized run %s -> %s", run_id, dest)
        return dest
