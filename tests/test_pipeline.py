"""
Tests for the LangGraph dispatch pipeline.

Tests the full pipeline end-to-end using StubClient (no API key needed).
Verifies the graph compiles, executes, and produces expected state.
"""

import sys
from pathlib import Path

import pytest
from unittest.mock import patch

# Add paths for imports
_src_path = str(Path(__file__).resolve().parents[1] / "src")
_repo_root = str(Path(__file__).resolve().parents[1])
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from ai_ops.llm.client import StubClient
from ai_ops.runtime.approval import AutoApprovalHandler
from ai_ops.runtime.persistence import RunPersistence

from workflows.langgraph.graphs.dispatch_pipeline import create_pipeline


@pytest.fixture
def stub_pipeline(tmp_path):
    """Create a pipeline with StubClient and temp persistence."""
    repo_root = tmp_path / "ai-ops"
    (repo_root / "runs" / "active").mkdir(parents=True)
    (repo_root / "runs" / "completed").mkdir(parents=True)
    (repo_root / "runs" / "failed").mkdir(parents=True)
    (repo_root / "memory" / "run-summaries").mkdir(parents=True)

    return create_pipeline(
        llm_client=StubClient(),
        approval_handler=AutoApprovalHandler(),
        persistence=RunPersistence(repo_root=repo_root),
        persist_results=True,
    ), repo_root


class TestPipelineCreation:
    """Test pipeline compilation."""

    def test_pipeline_compiles(self):
        pipeline = create_pipeline(
            llm_client=StubClient(),
            persist_results=False,
        )
        assert pipeline is not None

    def test_pipeline_compiles_with_defaults(self):
        pipeline = create_pipeline(
            llm_client=StubClient(),
            persist_results=False,
        )
        assert pipeline is not None


class TestPipelineExecution:
    """Test full pipeline runs."""

    def test_full_pipeline_completes(self, stub_pipeline):
        pipeline, repo_root = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-pipeline-001",
            "task_description": "Build a user authentication module",
            "acceptance_criteria": ["JWT support", "Password hashing"],
            "constraints": ["Python 3.11+"],
            "approval_level": 0,
        })

        assert result["status"] in ("completed", "failed")
        assert result["current_stage"] == "done"
        assert "dispatcher_output" in result
        assert "research_output" in result
        assert "builder_output" in result
        assert "reviewer_output" in result

    def test_pipeline_dispatcher_output(self, stub_pipeline):
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-pipeline-002",
            "task_description": "Research Python frameworks",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        dispatcher_out = result["dispatcher_output"]
        assert "classification" in dispatcher_out
        assert "plan" in dispatcher_out

    def test_pipeline_reviewer_verdict(self, stub_pipeline):
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-pipeline-003",
            "task_description": "Build something",
            "acceptance_criteria": ["Works correctly"],
            "constraints": [],
            "approval_level": 0,
        })

        reviewer_out = result.get("reviewer_output", {})
        assert "verdict" in reviewer_out

    def test_pipeline_no_errors(self, stub_pipeline):
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-pipeline-004",
            "task_description": "Simple task",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert len(result.get("errors", [])) == 0

    def test_pipeline_approval_tracking(self, stub_pipeline):
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-pipeline-005",
            "task_description": "Build something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        decisions = result.get("approval_decisions", [])
        assert len(decisions) >= 1
        assert decisions[0]["result"] == "approved"


class TestPipelinePersistence:
    """Test that the pipeline persists results."""

    def test_run_summary_persisted(self, stub_pipeline):
        pipeline, repo_root = stub_pipeline
        pipeline.invoke({
            "run_id": "test-persist-001",
            "task_description": "Build auth",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        summary_path = repo_root / "memory" / "run-summaries" / "test-persist-001.yaml"
        assert summary_path.exists()

    def test_agent_outputs_persisted(self, stub_pipeline):
        pipeline, repo_root = stub_pipeline
        pipeline.invoke({
            "run_id": "test-persist-002",
            "task_description": "Build something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        # Run should be finalized to completed/
        completed_dir = repo_root / "runs" / "completed" / "test-persist-002"
        assert completed_dir.exists()

        # Check that agent outputs exist
        assert (completed_dir / "dispatcher-output.yaml").exists()
        assert (completed_dir / "artifact-index.yaml").exists()

    def test_run_finalized_to_completed(self, stub_pipeline):
        pipeline, repo_root = stub_pipeline
        pipeline.invoke({
            "run_id": "test-persist-003",
            "task_description": "Build auth",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        # Should not be in active anymore
        assert not (repo_root / "runs" / "active" / "test-persist-003").exists()
        # Should be in completed
        assert (repo_root / "runs" / "completed" / "test-persist-003").exists()

    def test_reviewer_fail_goes_to_completed_not_failed(self, stub_pipeline, monkeypatch):
        """Reviewer FAIL (needs_revision) must land in completed/, not failed/."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        def fail_verdict(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {"verdict": "FAIL", "verdict_reason": "Injected FAIL"}
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", fail_verdict)
        pipeline, repo_root = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-persist-004",
            "task_description": "Build something",
            "acceptance_criteria": ["Works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result["status"] == "needs_revision"   # not overwritten to "failed"
        assert (repo_root / "runs" / "completed" / "test-persist-004").exists()
        assert not (repo_root / "runs" / "failed" / "test-persist-004").exists()


class TestPipelineApprovalGating:
    """Test approval gating in the pipeline."""

    def test_level_0_proceeds(self, stub_pipeline):
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-approval-001",
            "task_description": "Read docs",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })
        assert result["status"] in ("completed",)

    def test_level_3_blocked(self):
        """Level 3 should block the pipeline."""
        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persist_results=False,
        )
        result = pipeline.invoke({
            "run_id": "test-approval-002",
            "task_description": "Delete production data",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 3,
        })
        assert result["status"] in ("blocked",)

    def test_level_2_denied_auto(self):
        """Level 2 with AutoApprovalHandler should be denied."""
        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persist_results=False,
        )
        result = pipeline.invoke({
            "run_id": "test-approval-003",
            "task_description": "Merge to main",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 2,
        })
        assert result["status"] in ("denied",)

    def test_level_3_blocked_has_no_dispatcher_schema_noise(self, stub_pipeline):
        """Blocked run: only the approval error in state["errors"], no dispatcher schema errors."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-blocked-errors-001",
            "task_description": "Delete all production data",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 3,
        })
        assert result["status"] == "blocked"
        errors = result.get("errors", [])
        # No spurious schema or routing-guard errors from the empty dispatcher result
        noisy = [e for e in errors if "schema invalid" in e or "required_agents" in e]
        assert noisy == [], f"Unexpected dispatcher noise in errors: {noisy}"
        # The real block error must still be present
        assert any("blocked" in e.lower() for e in errors)

    def test_level_2_denied_clean_behavior(self, stub_pipeline):
        """Denied run (L2): correct status, no dispatcher schema noise, lands in failed/."""
        pipeline, repo_root = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-denied-001",
            "task_description": "Merge feature branch to main",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 2,
        })
        # Status preserved correctly
        assert result["status"] == "denied"
        assert result["current_stage"] == "done"
        errors = result.get("errors", [])
        # No spurious schema or routing-guard errors from the empty dispatcher result
        noisy = [e for e in errors if "schema invalid" in e or "required_agents" in e]
        assert noisy == [], f"Unexpected dispatcher noise in errors: {noisy}"
        # The real denial message must be present
        assert any("denied" in e.lower() for e in errors)
        # Run lands in failed/, not completed/
        assert (repo_root / "runs" / "failed" / "test-denied-001").exists()
        assert not (repo_root / "runs" / "completed" / "test-denied-001").exists()

    def test_level_3_blocked_goes_to_failed_directory(self, stub_pipeline):
        """Blocked run must land in runs/failed/, not runs/completed/."""
        pipeline, repo_root = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-block-persist-001",
            "task_description": "Delete production data",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 3,
        })
        assert result["status"] == "blocked"
        assert (repo_root / "runs" / "failed" / "test-block-persist-001").exists()
        assert not (repo_root / "runs" / "completed" / "test-block-persist-001").exists()


class TestSchemaValidation:
    """Pydantic schema validation at dispatcher_node and reviewer_node boundaries."""

    def test_valid_stub_output_no_schema_errors(self, stub_pipeline):
        """Stub output must pass both schemas — no schema errors appended."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-001",
            "task_description": "Build a feature",
            "acceptance_criteria": ["It works"],
            "constraints": [],
            "approval_level": 0,
        })
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert schema_errors == []

    def test_invalid_dispatcher_classification_adds_error(self, stub_pipeline, monkeypatch):
        """Malformed classification dict: schema error added, pipeline still reaches done."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def bad_execute(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {"not_a_valid_field": True},  # missing task_type, complexity, etc.
                "plan": {"run_id": "x", "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", bad_execute)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-002",
            "task_description": "Build a feature",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert len(schema_errors) >= 1
        assert "classification" in schema_errors[0]

    def test_invalid_reviewer_output_adds_error(self, stub_pipeline, monkeypatch):
        """Bad verdict enum value: schema error added, pipeline still reaches done."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        def bad_execute(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "verdict": "NOT_A_REAL_VERDICT",  # not a valid ReviewVerdict value
                "verdict_reason": "injected bad output",
            }
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", bad_execute)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-003",
            "task_description": "Build something",  # routes to research→builder→reviewer
            "acceptance_criteria": ["Works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert len(schema_errors) >= 1
        assert "reviewer" in schema_errors[0]

    def test_invalid_research_output_adds_error(self, stub_pipeline, monkeypatch):
        """Missing required field: schema error added, pipeline still reaches done."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.research import ResearchAgent

        def bad_execute(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                # missing required field: research_question
                "findings": [],
            }
            return output

        monkeypatch.setattr(ResearchAgent, "execute", bad_execute)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-004",
            "task_description": "Build something",
            "acceptance_criteria": ["Works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert len(schema_errors) >= 1
        assert "research" in schema_errors[0]

    def test_invalid_builder_output_adds_error(self, stub_pipeline, monkeypatch):
        """Missing required field: schema error added, pipeline still reaches done."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent

        def bad_execute(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                # missing required field: implementation_summary
                "files_changed": {},
            }
            return output

        monkeypatch.setattr(BuilderAgent, "execute", bad_execute)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-005",
            "task_description": "Build something",
            "acceptance_criteria": ["Works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert len(schema_errors) >= 1
        assert "builder" in schema_errors[0]

    def test_research_smoke002_nested_shape_produces_schema_error(self, stub_pipeline, monkeypatch):
        """Regression: smoke-002 LLM nested output (outputs.research_report wrapper) fails schema.

        The live LLM returned content under outputs.research_report instead of flat top-level
        fields. ResearchOutput requires research_question at the top level — this shape must
        produce a schema error so the contract mismatch is operator-visible.
        """
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.research import ResearchAgent

        def smoke002_shape(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            # Exact structure returned by smoke-002 live run — research_question nested, not flat
            output.result = {
                "status": "completed",
                "run_id": agent_input.run_id,
                "subtask_id": 1,
                "agent": "research",
                "outputs": {
                    "research_report": {
                        "title": "Research Report: Python Logging Best Practices",
                        "research_question": "What are the best practices for Python logging?",
                        "key_findings": ["Use module-level loggers"],
                        "recommendations": ["Use dictConfig"],
                    }
                },
                "next_agent": "reviewer",
            }
            return output

        monkeypatch.setattr(ResearchAgent, "execute", smoke002_shape)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-smoke002-research",
            "task_description": "Research Python logging",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert len(schema_errors) >= 1, "Expected schema error for smoke-002 nested research shape"
        assert "research" in schema_errors[0]

    def test_builder_smoke002_message_shape_produces_schema_error(self, stub_pipeline, monkeypatch):
        """Regression: smoke-002 LLM output used 'message' key instead of 'implementation_summary'.

        BuilderOutput requires implementation_summary — the message-keyed shape must produce a
        schema error so the contract mismatch is operator-visible.
        """
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent

        def smoke002_shape(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            # Exact structure returned by smoke-002 live run — 'message' key, not 'implementation_summary'
            output.result = {
                "status": "completed",
                "message": "Research task completed successfully. The research output provides "
                           "comprehensive coverage of Python logging best practices.",
                "task_type": "research",
                "completion_time": "2024-12-19T10:15:30Z",
                "research_context_received": True,
            }
            return output

        monkeypatch.setattr(BuilderAgent, "execute", smoke002_shape)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-smoke002-builder",
            "task_description": "Build something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert len(schema_errors) >= 1, "Expected schema error for smoke-002 message-keyed builder shape"
        assert "builder" in schema_errors[0]

    def test_research_flat_conformant_shape_passes_validation(self, stub_pipeline, monkeypatch):
        """Flat research output matching the JSON Output Contract must produce no schema errors."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.research import ResearchAgent

        def conformant_shape(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "research_question": "What are the best practices for Python logging?",
                "scope": {"included": ["stdlib logging"], "excluded": ["loguru"]},
                "findings": [{"id": 1, "finding": "Use module-level loggers", "evidence": "docs", "confidence": "high"}],
                "assumptions": ["Python 3.6+"],
                "recommendations": {"recommended": "dictConfig", "alternatives": [], "not_recommended": []},
                "gaps": [],
                "sources": ["https://docs.python.org/3/howto/logging.html"],
            }
            return output

        monkeypatch.setattr(ResearchAgent, "execute", conformant_shape)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-conformant-research",
            "task_description": "Research Python logging",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        research_errors = [e for e in result.get("errors", []) if "research" in e and "schema invalid" in e]
        assert research_errors == [], f"Schema-conformant research output must not produce errors: {research_errors}"

    def test_builder_flat_conformant_shape_passes_validation(self, stub_pipeline, monkeypatch):
        """Flat builder output with implementation_summary must produce no schema errors."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent

        def conformant_shape(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "implementation_summary": "Implemented Python logging configuration using dictConfig.",
                "files_changed": {"created": ["src/logging_config.py"], "modified": [], "deleted": []},
                "tests_created": ["tests/test_logging_config.py"],
                "dependencies_added": [],
                "deviations_from_plan": "none",
                "known_limitations": [],
                "research_context_received": True,
            }
            return output

        monkeypatch.setattr(BuilderAgent, "execute", conformant_shape)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-conformant-builder",
            "task_description": "Build something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        builder_errors = [e for e in result.get("errors", []) if "builder" in e and "schema invalid" in e]
        assert builder_errors == [], f"Schema-conformant builder output must not produce errors: {builder_errors}"

    def test_reviewer_smoke003_shape_passes_validation(self, stub_pipeline, monkeypatch):
        """Regression: smoke-003 live reviewer output shape must validate cleanly.

        The live LLM returned automated_checks and policy_compliance as lists (not dicts),
        and plan_adherence as a dict (not a string). These are the correct shapes.
        ReviewResult schema was updated to match — this test pins that contract.
        """
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        def smoke003_shape(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            # Exact structure from smoke-003 live run
            output.result = {
                "verdict": "PASS",
                "acceptance_criteria": [
                    {"criterion": "Research Python logging best practices", "status": "PASS", "notes": "Research completed"}
                ],
                "automated_checks": [
                    {"check": "Lint", "tool": "ruff", "status": "N/A", "details": "No code files to check"},
                    {"check": "Type check", "tool": "mypy", "status": "N/A", "details": "No code files to check"},
                    {"check": "Unit tests", "tool": "pytest", "status": "N/A", "details": "No tests expected"},
                    {"check": "Existing tests", "tool": "pytest", "status": "PASS", "details": "No regression risk"},
                ],
                "findings": [],
                "policy_compliance": [
                    {"policy": "Security rules", "status": "PASS", "notes": "No code changes"},
                    {"policy": "Naming conventions", "status": "PASS", "notes": "No code changes"},
                    {"policy": "Data handling", "status": "PASS", "notes": "No data handling code"},
                ],
                "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                "missing_items": [],
                "summary": "Research task completed successfully.",
                "recommendation": "approve",
                "build_context_received": True,
            }
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", smoke003_shape)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-smoke003-reviewer",
            "task_description": "Build something",
            "acceptance_criteria": ["Research completed"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        reviewer_errors = [e for e in result.get("errors", []) if "reviewer" in e and "schema invalid" in e]
        assert reviewer_errors == [], f"smoke-003 reviewer shape must pass schema validation: {reviewer_errors}"

    def test_reviewer_old_dict_shapes_produce_schema_error(self, stub_pipeline, monkeypatch):
        """Old dict-typed automated_checks/policy_compliance and str plan_adherence must fail.

        Prior to the smoke-003 fix the schema used dict/str types. Passing those old shapes
        must now trigger a schema error — confirming the contract was tightened.
        """
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        def old_dict_shape(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "verdict": "PASS",
                # Old stub shapes — dict where schema now expects list
                "automated_checks": {"lint": {"status": "not_run", "tool": "ruff"}},
                "policy_compliance": {"security_rules": "not_checked"},
                "plan_adherence": "not_verified",  # str where schema now expects dict
            }
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", old_dict_shape)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-schema-old-reviewer",
            "task_description": "Build something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        reviewer_errors = [e for e in result.get("errors", []) if "reviewer" in e and "schema invalid" in e]
        assert len(reviewer_errors) >= 1, "Old dict-typed reviewer output must produce schema error"


class TestDispatcherRouting:
    """Dispatcher required_agents routing guard — empty/missing must surface in errors."""

    def test_empty_required_agents_produces_error(self, stub_pipeline, monkeypatch):
        """Empty required_agents list: error recorded, status failed, no agents execute."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def empty_agents(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 0,
                    "required_agents": [],  # empty — routing guard should fire
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", empty_agents)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-routing-001",
            "task_description": "Do something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result["status"] == "failed"   # not "running"
        routing_errors = [e for e in result.get("errors", []) if "required_agents" in e]
        assert len(routing_errors) >= 1
        # No agents should have executed
        assert result.get("research_output") is None
        assert result.get("builder_output") is None
        assert result.get("reviewer_output") is None

    def test_missing_required_agents_produces_error(self, stub_pipeline, monkeypatch):
        """required_agents key absent from classification: error recorded, no agent execution."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def missing_agents(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 1,
                    # required_agents key omitted entirely
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", missing_agents)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-routing-002",
            "task_description": "Do something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        routing_errors = [e for e in result.get("errors", []) if "required_agents" in e]
        assert len(routing_errors) >= 1
        assert result.get("research_output") is None

    def test_unknown_required_agents_produces_error(self, stub_pipeline, monkeypatch):
        """All-unknown agent names: error in state["errors"], status failed, no agents execute."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def unknown_agents(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 1,
                    "required_agents": ["planner", "executor"],  # both unknown
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", unknown_agents)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-routing-003",
            "task_description": "Do something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result["status"] == "failed"   # not "running"
        routing_errors = [e for e in result.get("errors", []) if "required_agents" in e]
        assert len(routing_errors) >= 1
        assert result.get("research_output") is None
        assert result.get("builder_output") is None
        assert result.get("reviewer_output") is None

    def test_title_case_agent_names_normalized_and_route(self, stub_pipeline, monkeypatch):
        """LLM-style title-case names like Researcher/Reviewer are normalized and route correctly."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def title_case_agents(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 2,
                    "required_agents": ["Researcher", "Reviewer"],  # live LLM variant
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", title_case_agents)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-routing-005",
            "task_description": "Research and review something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        # No routing guard errors — normalization resolved the names
        routing_errors = [e for e in result.get("errors", []) if "required_agents" in e]
        assert routing_errors == []
        # research agent ran (Researcher → research)
        assert result.get("research_output") is not None
        # status is a proper terminal value
        assert result["status"] in ("completed", "needs_revision")

    def test_partially_unknown_required_agents_routes_normally(self, stub_pipeline, monkeypatch):
        """One known + one unknown agent: guard must NOT fire, pipeline routes normally."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def mixed_agents(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 1,
                    "required_agents": ["research", "unknown_agent"],  # one known, one not
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", mixed_agents)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-routing-004",
            "task_description": "Do something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        # No routing guard error — intersection with known agents is non-empty
        routing_errors = [e for e in result.get("errors", []) if "required_agents" in e]
        assert routing_errors == []
        # research agent ran (it's in the known intersection)
        assert result.get("research_output") is not None


class TestConditionalRouting:
    """Inter-node routing respects required_agents throughout the chain, not just at entry."""

    def test_research_only_skips_builder_and_reviewer(self, stub_pipeline, monkeypatch):
        """required_agents=['research'] must skip builder and reviewer entirely."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def research_only(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 1,
                    "required_agents": ["research"],
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", research_only)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-cr-001",
            "task_description": "Research something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result["status"] == "completed"
        assert result.get("research_output") is not None
        assert result.get("builder_output") is None
        assert result.get("reviewer_output") is None
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert schema_errors == []

    def test_research_plus_reviewer_skips_builder(self, stub_pipeline, monkeypatch):
        """required_agents=['research','reviewer'] must skip builder but run reviewer."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def research_and_reviewer(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 2,
                    "required_agents": ["research", "reviewer"],
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", research_and_reviewer)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-cr-002",
            "task_description": "Research and review something",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result.get("research_output") is not None
        assert result.get("builder_output") is None
        assert result.get("reviewer_output") is not None

    def test_full_chain_still_runs_when_all_three_required(self, stub_pipeline):
        """Default stub (all three agents) must still run all three — regression guard."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-cr-003",
            "task_description": "Build a full feature",
            "acceptance_criteria": ["Works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result.get("research_output") is not None
        assert result.get("builder_output") is not None
        assert result.get("reviewer_output") is not None

    def test_research_only_status_is_completed_not_needs_revision(self, stub_pipeline, monkeypatch):
        """Research-only run must complete as 'completed', not 'needs_revision'.

        needs_revision only arises from a reviewer FAIL. If reviewer never runs,
        the run must reach completed status.
        """
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def research_only(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 1,
                    "required_agents": ["research"],
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", research_only)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-cr-004",
            "task_description": "Research only task",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["status"] == "completed", (
            f"Expected 'completed', got {result['status']!r}. "
            "Reviewer must not run for research-only tasks."
        )
        assert result["status"] != "needs_revision"

    def test_research_only_summary_persists_completed_not_running(self, stub_pipeline, monkeypatch):
        """Regression: run summary must record 'completed', not 'running', for research-only runs.

        Root cause (smoke-007): save_run_summary was called before the 'running' → 'completed'
        resolution in persist_node, so the summary file always wrote status: running.
        """
        import yaml
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def research_only(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 1,
                    "required_agents": ["research"],
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", research_only)
        pipeline, repo_root = stub_pipeline
        pipeline.invoke({
            "run_id": "test-cr-005",
            "task_description": "Research only task",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        summary_path = repo_root / "memory" / "run-summaries" / "test-cr-005.yaml"
        assert summary_path.exists(), "Run summary file must be written"
        summary = yaml.safe_load(summary_path.read_text())
        assert summary["status"] == "completed", (
            f"Summary must record 'completed', got {summary['status']!r}. "
            "save_run_summary must be called after status resolution."
        )


class TestReviewerContext:
    """Reviewer receives task_type and research_output in context for research+review runs."""

    def test_reviewer_receives_research_output_and_task_type(self, stub_pipeline, monkeypatch):
        """reviewer_node must pass research_output and task_type into AgentInput context."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent
        from ai_ops.agents.reviewer import ReviewerAgent

        def research_and_reviewer(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 2,
                    "required_agents": ["research", "reviewer"],
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        captured = {}

        def capturing_reviewer(self, agent_input, output):
            captured["context"] = agent_input.context
            output.status = TaskStatus.COMPLETED
            output.result = {
                "verdict": "PASS",
                "verdict_reason": "Research is thorough",
                "acceptance_criteria": [],
                "automated_checks": [],
                "findings": [],
                "policy_compliance": [],
                "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                "missing_items": [],
                "summary": "Research review passed.",
                "recommendation": "approve",
                "build_context_received": False,
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", research_and_reviewer)
        monkeypatch.setattr(ReviewerAgent, "execute", capturing_reviewer)
        pipeline, _ = stub_pipeline
        pipeline.invoke({
            "run_id": "test-rc-001",
            "task_description": "Research Python CLI best practices",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        ctx = captured.get("context", {})
        assert "research_output" in ctx, "reviewer must receive research_output in context"
        assert ctx["research_output"], "research_output must be non-empty for research+review run"
        assert "task_type" in ctx, "reviewer must receive task_type in context"
        assert ctx["task_type"] == "research"
        assert "build_output" in ctx, "build_output key must still be present (may be empty)"

    def test_research_review_run_completes_without_schema_errors(self, stub_pipeline, monkeypatch):
        """research+reviewer routing must complete as 'completed' with no schema errors."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def research_and_reviewer(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "research",
                    "complexity": "simple",
                    "estimated_subtasks": 2,
                    "required_agents": ["research", "reviewer"],
                },
                "plan": {"run_id": agent_input.run_id, "subtasks": [], "execution_order": []},
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", research_and_reviewer)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-rc-002",
            "task_description": "Research Python CLI best practices",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        assert result.get("research_output") is not None
        assert result.get("builder_output") is None
        assert result.get("reviewer_output") is not None
        schema_errors = [e for e in result.get("errors", []) if "schema invalid" in e]
        assert schema_errors == [], f"Unexpected schema errors: {schema_errors}"
