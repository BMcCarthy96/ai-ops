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


class TestAgentAliasNormalization:
    """Canonical agent-role normalization: LLM-produced names map to runtime roles."""

    # ------------------------------------------------------------------
    # Direct alias map unit tests
    # ------------------------------------------------------------------

    def test_codebuilder_alias_maps_to_builder(self):
        """Regression guard for smoke-026: 'codebuilder' must map to 'builder'."""
        from workflows.langgraph.graphs.dispatch_pipeline import _AGENT_NAME_ALIASES

        assert _AGENT_NAME_ALIASES.get("codebuilder") == "builder", (
            "'codebuilder' not in alias map — smoke-026 regression"
        )

    def test_all_builder_synonyms_normalize_to_builder(self):
        """Every known builder synonym lowercases and resolves to 'builder'."""
        from workflows.langgraph.graphs.dispatch_pipeline import _AGENT_NAME_ALIASES

        builder_variants = [
            "builder", "Builder", "BUILDER",
            "engineer", "Engineer",
            "developer", "Developer",
            "dev", "Dev",
            "codebuilder", "CodeBuilder",   # smoke-026
            "coder", "Coder",
            "programmer", "Programmer",
            "implementer", "Implementer",
            "implementation", "Implementation",
        ]
        for variant in builder_variants:
            canonical = _AGENT_NAME_ALIASES.get(variant.lower(), variant.lower())
            assert canonical == "builder", (
                f"{variant!r} (lowercased: {variant.lower()!r}) did not resolve to 'builder', got {canonical!r}"
            )

    def test_research_and_reviewer_new_aliases_normalize(self):
        """Spot-check new research and reviewer aliases."""
        from workflows.langgraph.graphs.dispatch_pipeline import _AGENT_NAME_ALIASES

        cases = [
            ("analyst", "research"),
            ("Analyst", "research"),
            ("investigator", "research"),
            ("analysis", "research"),
            ("evaluator", "reviewer"),
            ("Evaluator", "reviewer"),
            ("validator", "reviewer"),
            ("verifier", "reviewer"),
            ("checker", "reviewer"),
        ]
        for raw, expected in cases:
            canonical = _AGENT_NAME_ALIASES.get(raw.lower(), raw.lower())
            assert canonical == expected, (
                f"{raw!r} expected to resolve to {expected!r}, got {canonical!r}"
            )

    # ------------------------------------------------------------------
    # Integration: CodeBuilder routes to builder node
    # ------------------------------------------------------------------

    def test_codebuilder_in_required_agents_routes_to_builder(self, stub_pipeline, monkeypatch):
        """When dispatcher produces 'CodeBuilder', builder node must run — not be skipped."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def codebuilder_dispatch(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "build",
                    "complexity": "simple",
                    "estimated_subtasks": 2,
                    "required_agents": ["CodeBuilder", "Reviewer"],
                },
                "plan": {
                    "run_id": agent_input.run_id,
                    "subtasks": [
                        {
                            "id": 1,
                            "assigned_agent": "CodeBuilder",
                            "description": agent_input.description,
                            "depends_on": [],
                            "approval_level": 0,
                        },
                        {
                            "id": 2,
                            "assigned_agent": "Reviewer",
                            "description": agent_input.description,
                            "depends_on": [1],
                            "approval_level": 0,
                        },
                    ],
                    "execution_order": [1, 2],
                },
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", codebuilder_dispatch)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "alias-norm-001",
            "task_description": "Implement a stack",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        # Builder must have run — builder_output present
        assert result.get("builder_output"), (
            "builder_output missing — builder node was skipped despite 'CodeBuilder' in plan"
        )
        # Reviewer must also have run
        assert result.get("reviewer_output"), "reviewer_output missing"
        # No routing guard error
        routing_errors = [e for e in result.get("errors", []) if "required_agents" in e]
        assert routing_errors == [], f"Unexpected routing errors: {routing_errors}"

    # ------------------------------------------------------------------
    # _get_subtask_for_agent with CodeBuilder assigned_agent
    # ------------------------------------------------------------------

    def test_codebuilder_subtask_resolved_by_get_subtask_for_agent(self):
        """_get_subtask_for_agent returns the builder subtask when assigned_agent is 'CodeBuilder'."""
        from workflows.langgraph.graphs.dispatch_pipeline import _get_subtask_for_agent

        state = {
            "dispatcher_output": {
                "plan": {
                    "subtasks": [
                        {"id": 1, "description": "Build it", "assigned_agent": "CodeBuilder"},
                        {"id": 2, "description": "Review it", "assigned_agent": "Reviewer"},
                    ]
                }
            }
        }

        builder_subtask = _get_subtask_for_agent(state, "builder")
        reviewer_subtask = _get_subtask_for_agent(state, "reviewer")
        research_subtask = _get_subtask_for_agent(state, "research")

        assert builder_subtask is not None, (
            "_get_subtask_for_agent returned None for 'CodeBuilder' — alias not applied"
        )
        assert builder_subtask["id"] == 1
        assert reviewer_subtask is not None
        assert reviewer_subtask["id"] == 2
        assert research_subtask is None  # not in plan — correct

    # ------------------------------------------------------------------
    # Deduplicate normalized required_agents (smoke-031 regression guard)
    # ------------------------------------------------------------------

    def test_duplicate_synonyms_deduplicated_in_required_agents(self, stub_pipeline, monkeypatch):
        """Synonyms that resolve to the same role must appear only once after normalization.

        Regression guard for smoke-031: ['Coder', 'Tester', 'Reviewer'] all collapsed
        to ['builder', 'reviewer', 'reviewer'] before the fix — reviewer appeared twice.
        """
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent

        def duplicate_synonyms(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "classification": {
                    "task_type": "build",
                    "complexity": "simple",
                    "estimated_subtasks": 2,
                    # 'Coder' → builder, 'Tester' → reviewer, 'Reviewer' → reviewer
                    "required_agents": ["Coder", "Tester", "Reviewer"],
                },
                "plan": {
                    "run_id": agent_input.run_id,
                    "subtasks": [
                        {
                            "id": 1,
                            "assigned_agent": "Coder",
                            "description": agent_input.description,
                            "depends_on": [],
                            "approval_level": 0,
                        },
                        {
                            "id": 2,
                            "assigned_agent": "Reviewer",
                            "description": agent_input.description,
                            "depends_on": [1],
                            "approval_level": 0,
                        },
                    ],
                    "execution_order": [1, 2],
                },
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", duplicate_synonyms)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "alias-norm-dedup-001",
            "task_description": "Implement a queue",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["current_stage"] == "done"
        # Builder and reviewer each appear exactly once in required_agents
        required = (
            result.get("dispatcher_output", {})
            .get("classification", {})
            .get("required_agents", [])
        )
        assert required.count("builder") == 1, f"'builder' duplicated: {required}"
        assert required.count("reviewer") == 1, f"'reviewer' duplicated: {required}"
        assert len(required) == 2, f"Expected exactly 2 agents, got {required}"
        # Pipeline must have routed correctly
        assert result.get("builder_output"), "builder node did not run"
        assert result.get("reviewer_output"), "reviewer node did not run"

    def test_deduplicated_required_agents_preserves_order(self):
        """Deduplication preserves first-occurrence order, not last."""
        # Simulate the normalization expression in dispatcher_node directly
        from workflows.langgraph.graphs.dispatch_pipeline import _AGENT_NAME_ALIASES

        raw = ["Researcher", "Coder", "Tester", "Reviewer", "Analyst"]
        aliased = [
            _AGENT_NAME_ALIASES.get(n.lower(), n.lower())
            for n in raw
        ]
        deduped = list(dict.fromkeys(aliased))

        # research appears first (Researcher), then builder (Coder), then reviewer (Tester)
        # Analyst → research (duplicate, dropped); Reviewer → reviewer (duplicate, dropped)
        assert deduped == ["research", "builder", "reviewer"], (
            f"Unexpected deduped order: {deduped}"
        )


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


class TestSubtaskPropagation:
    """Dispatcher subtask assignments reach the executing agents."""

    # Shared dispatcher output with a plan containing one subtask per agent.
    _PLAN_WITH_SUBTASKS = {
        "classification": {
            "task_type": "build",
            "complexity": "moderate",
            "estimated_subtasks": 3,
            "required_agents": ["research", "builder", "reviewer"],
        },
        "plan": {
            "run_id": "test-sub-run",
            "subtasks": [
                {
                    "id": 1,
                    "description": "Specific research subtask: investigate JWT libraries",
                    "assigned_agent": "Researcher",
                    "skills": ["research"],
                    "inputs": [],
                    "outputs": ["jwt_comparison"],
                    "depends_on": [],
                    "approval_level": 0,
                },
                {
                    "id": 2,
                    "description": "Specific builder subtask: implement JWT module",
                    "assigned_agent": "Builder",
                    "skills": ["coding"],
                    "inputs": ["jwt_comparison"],
                    "outputs": ["auth/jwt.py"],
                    "depends_on": [1],
                    "approval_level": 0,
                },
                {
                    "id": 3,
                    "description": "Specific reviewer subtask: verify JWT implementation",
                    "assigned_agent": "Reviewer",
                    "skills": ["qa"],
                    "inputs": ["auth/jwt.py"],
                    "outputs": ["review_report"],
                    "depends_on": [2],
                    "approval_level": 0,
                },
            ],
            "execution_order": [1, 2, 3],
            "estimated_total_time": "30 minutes",
        },
    }

    def test_research_node_uses_subtask_description(self, stub_pipeline, monkeypatch):
        """Research agent must receive its specific subtask description, not task_description."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent
        from ai_ops.agents.research import ResearchAgent

        plan = self._PLAN_WITH_SUBTASKS

        def planned_dispatcher(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = plan
            return output

        captured = {}

        def capturing_research(self, agent_input, output):
            captured["description"] = agent_input.description
            captured["subtask"] = agent_input.context.get("subtask", {})
            output.status = TaskStatus.COMPLETED
            output.result = {
                "research_question": agent_input.description,
                "scope": {}, "findings": [], "assumptions": [],
                "recommendations": {}, "gaps": [], "sources": [],
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", planned_dispatcher)
        monkeypatch.setattr(ResearchAgent, "execute", capturing_research)
        pipeline, _ = stub_pipeline
        pipeline.invoke({
            "run_id": "test-sub-001",
            "task_description": "FULL TASK — should not reach research",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert captured["description"] == "Specific research subtask: investigate JWT libraries"
        assert captured["subtask"].get("id") == 1
        assert captured["subtask"].get("assigned_agent") == "Researcher"

    def test_builder_node_uses_subtask_description(self, stub_pipeline, monkeypatch):
        """Builder agent must receive its specific subtask description, not task_description."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent
        from ai_ops.agents.builder import BuilderAgent

        plan = self._PLAN_WITH_SUBTASKS

        def planned_dispatcher(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = plan
            return output

        captured = {}

        def capturing_builder(self, agent_input, output):
            captured["description"] = agent_input.description
            captured["subtask"] = agent_input.context.get("subtask", {})
            output.status = TaskStatus.COMPLETED
            output.result = {
                "implementation_summary": agent_input.description,
                "files_changed": {}, "tests_created": [],
                "dependencies_added": [], "deviations_from_plan": "none",
                "known_limitations": [], "research_context_received": True,
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", planned_dispatcher)
        monkeypatch.setattr(BuilderAgent, "execute", capturing_builder)
        pipeline, _ = stub_pipeline
        pipeline.invoke({
            "run_id": "test-sub-002",
            "task_description": "FULL TASK — should not reach builder",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert captured["description"] == "Specific builder subtask: implement JWT module"
        assert captured["subtask"].get("id") == 2
        assert captured["subtask"].get("assigned_agent") == "Builder"

    def test_agents_fall_back_to_task_description_when_no_plan(self, stub_pipeline, monkeypatch):
        """When dispatcher returns no subtasks, agents must use task_description unchanged."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.dispatcher import DispatcherAgent
        from ai_ops.agents.research import ResearchAgent

        def no_plan_dispatcher(self, agent_input, output):
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

        captured = {}

        def capturing_research(self, agent_input, output):
            captured["description"] = agent_input.description
            captured["subtask"] = agent_input.context.get("subtask", {})
            output.status = TaskStatus.COMPLETED
            output.result = {
                "research_question": agent_input.description,
                "scope": {}, "findings": [], "assumptions": [],
                "recommendations": {}, "gaps": [], "sources": [],
            }
            return output

        monkeypatch.setattr(DispatcherAgent, "execute", no_plan_dispatcher)
        monkeypatch.setattr(ResearchAgent, "execute", capturing_research)
        pipeline, _ = stub_pipeline
        pipeline.invoke({
            "run_id": "test-sub-003",
            "task_description": "Fallback task description",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        assert captured["description"] == "Fallback task description"
        assert captured["subtask"] == {}

    def test_subtask_alias_matching_resolves_title_case(self, stub_pipeline, monkeypatch):
        """_get_subtask_for_agent must find subtasks assigned to 'Researcher' for agent 'research'."""
        from workflows.langgraph.graphs.dispatch_pipeline import _get_subtask_for_agent

        state = {
            "dispatcher_output": {
                "plan": {
                    "subtasks": [
                        {"id": 1, "description": "Do research", "assigned_agent": "Researcher"},
                        {"id": 2, "description": "Do build", "assigned_agent": "Engineer"},
                    ]
                }
            }
        }

        research_subtask = _get_subtask_for_agent(state, "research")
        builder_subtask = _get_subtask_for_agent(state, "builder")
        reviewer_subtask = _get_subtask_for_agent(state, "reviewer")

        assert research_subtask is not None
        assert research_subtask["id"] == 1
        assert builder_subtask is not None
        assert builder_subtask["id"] == 2
        assert reviewer_subtask is None  # not in plan — correct fallback signal


class TestReviewerCriteria:
    """Per-criterion structured evaluation in reviewer output."""

    def test_stub_produces_one_entry_per_criterion(self, stub_pipeline):
        """Stub reviewer must produce exactly one acceptance_criteria entry per input criterion."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-crit-001",
            "task_description": "Build a feature",
            "acceptance_criteria": ["Uses argparse", "Has --verbose flag", "Has tests"],
            "constraints": [],
            "approval_level": 0,
        })

        reviewer_out = result.get("reviewer_output", {})
        criteria = reviewer_out.get("acceptance_criteria", [])
        assert len(criteria) == 3, f"Expected 3 criterion entries, got {len(criteria)}"
        criterion_texts = [c["criterion"] for c in criteria]
        assert "Uses argparse" in criterion_texts
        assert "Has --verbose flag" in criterion_texts
        assert "Has tests" in criterion_texts

    def test_stub_criterion_status_values_are_uppercase(self, stub_pipeline):
        """Stub criterion status must be uppercase PASS/FAIL/PARTIAL per the JSON contract."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-crit-002",
            "task_description": "Build a feature",
            "acceptance_criteria": ["criterion A", "criterion B"],
            "constraints": [],
            "approval_level": 0,
        })

        criteria = result.get("reviewer_output", {}).get("acceptance_criteria", [])
        valid_statuses = {"PASS", "FAIL", "PARTIAL"}
        for entry in criteria:
            assert entry["status"] in valid_statuses, (
                f"Criterion status {entry['status']!r} is not uppercase. "
                f"Must be one of {valid_statuses}."
            )

    def test_stub_criterion_entries_have_required_fields(self, stub_pipeline):
        """Each acceptance_criteria entry must have criterion, status, and notes."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-crit-003",
            "task_description": "Build a feature",
            "acceptance_criteria": ["Must work"],
            "constraints": [],
            "approval_level": 0,
        })

        criteria = result.get("reviewer_output", {}).get("acceptance_criteria", [])
        assert len(criteria) >= 1
        for entry in criteria:
            assert "criterion" in entry, f"Missing 'criterion' key in entry: {entry}"
            assert "status" in entry, f"Missing 'status' key in entry: {entry}"
            assert "notes" in entry, f"Missing 'notes' key in entry: {entry}"

    def test_empty_criteria_produces_empty_list(self, stub_pipeline):
        """When no acceptance_criteria are provided, reviewer output list must be empty."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-crit-004",
            "task_description": "Build a feature",
            "acceptance_criteria": [],
            "constraints": [],
            "approval_level": 0,
        })

        criteria = result.get("reviewer_output", {}).get("acceptance_criteria", [])
        assert criteria == [], f"Expected empty list for no criteria, got: {criteria}"

    def test_injected_fail_verdict_produces_fail_criteria(self, stub_pipeline, monkeypatch):
        """A reviewer that FAILs a criterion must surface it in acceptance_criteria with FAIL status."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        def failing_reviewer(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "verdict": "FAIL",
                "verdict_reason": "JWT support not implemented",
                "acceptance_criteria": [
                    {"criterion": "JWT support", "status": "FAIL",
                     "notes": "No JWT code found in build output"},
                    {"criterion": "Password hashing", "status": "PASS",
                     "notes": "bcrypt usage confirmed"},
                ],
                "automated_checks": [],
                "findings": [{"id": 1, "severity": "major", "file": "N/A",
                               "issue": "JWT not implemented", "suggestion": "Add auth/jwt.py"}],
                "policy_compliance": [],
                "plan_adherence": {"matches_plan": "NO", "deviations": "JWT module absent"},
                "missing_items": ["auth/jwt.py"],
                "summary": "JWT criterion failed.",
                "recommendation": "revise and re-review",
                "build_context_received": True,
            }
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", failing_reviewer)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-crit-005",
            "task_description": "Build auth module",
            "acceptance_criteria": ["JWT support", "Password hashing"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["status"] == "needs_revision"
        reviewer_out = result.get("reviewer_output", {})
        criteria = reviewer_out.get("acceptance_criteria", [])
        assert len(criteria) == 2
        fail_entries = [c for c in criteria if c["status"] == "FAIL"]
        pass_entries = [c for c in criteria if c["status"] == "PASS"]
        assert len(fail_entries) == 1, "Expected exactly one FAIL criterion"
        assert fail_entries[0]["criterion"] == "JWT support"
        assert len(pass_entries) == 1
        assert pass_entries[0]["criterion"] == "Password hashing"
        # Notes must be non-empty for failed criterion
        assert fail_entries[0]["notes"], "FAIL criterion must have non-empty notes"


class TestRevisionLoop:
    """Revision loop: reviewer FAIL routes back to builder, with hard retry cap."""

    def test_one_successful_retry_path(self, stub_pipeline, monkeypatch):
        """FAIL on first review, PASS on second → status completed, revision_count = 1."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        call_count = {"n": 0}

        def reviewer_fail_then_pass(self, agent_input, output):
            call_count["n"] += 1
            output.status = TaskStatus.COMPLETED
            if call_count["n"] == 1:
                output.result = {
                    "verdict": "FAIL",
                    "verdict_reason": "JWT not implemented yet",
                    "acceptance_criteria": [
                        {"criterion": "JWT support", "status": "FAIL",
                         "notes": "No JWT code found"},
                    ],
                    "automated_checks": [],
                    "findings": [{"id": 1, "severity": "major", "file": "N/A",
                                  "issue": "JWT missing", "suggestion": "Add auth/jwt.py"}],
                    "policy_compliance": [],
                    "plan_adherence": {"matches_plan": "NO", "deviations": "JWT absent"},
                    "missing_items": ["auth/jwt.py"],
                    "summary": "JWT not found.",
                    "recommendation": "revise and re-review",
                    "build_context_received": True,
                }
            else:
                output.result = {
                    "verdict": "PASS",
                    "verdict_reason": "All criteria met after revision",
                    "acceptance_criteria": [
                        {"criterion": "JWT support", "status": "PASS",
                         "notes": "JWT implemented in auth/jwt.py"},
                    ],
                    "automated_checks": [],
                    "findings": [],
                    "policy_compliance": [],
                    "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                    "missing_items": [],
                    "summary": "All good.",
                    "recommendation": "approve",
                    "build_context_received": True,
                }
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", reviewer_fail_then_pass)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-rev-001",
            "task_description": "Build auth module",
            "acceptance_criteria": ["JWT support"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["status"] == "completed", f"Expected completed, got {result['status']!r}"
        assert result["current_stage"] == "done"
        assert result["revision_count"] == 1
        assert call_count["n"] == 2  # reviewed twice: initial FAIL + successful retry
        # No escalation on successful retry
        assert not any("Revision limit" in e for e in result.get("escalations", []))

    def test_builder_receives_revision_feedback_on_retry(self, stub_pipeline, monkeypatch):
        """On a revision run, builder context must contain revision_feedback with failed criteria."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent
        from ai_ops.agents.reviewer import ReviewerAgent

        captured_contexts = []

        def capturing_builder(self, agent_input, output):
            captured_contexts.append(dict(agent_input.context))
            output.status = TaskStatus.COMPLETED
            output.result = {
                "implementation_summary": "Built it",
                "files_changed": {}, "tests_created": [],
                "dependencies_added": [], "deviations_from_plan": "none",
                "known_limitations": [], "research_context_received": False,
            }
            return output

        reviewer_calls = {"n": 0}

        def reviewer_fail_then_pass(self, agent_input, output):
            reviewer_calls["n"] += 1
            output.status = TaskStatus.COMPLETED
            if reviewer_calls["n"] == 1:
                output.result = {
                    "verdict": "FAIL",
                    "verdict_reason": "Tests missing",
                    "acceptance_criteria": [
                        {"criterion": "Has tests", "status": "FAIL",
                         "notes": "No test files found"},
                        {"criterion": "Has docs", "status": "PASS",
                         "notes": "README present"},
                    ],
                    "automated_checks": [], "findings": [],
                    "policy_compliance": [],
                    "plan_adherence": {"matches_plan": "PARTIAL", "deviations": "tests absent"},
                    "missing_items": [], "summary": "Tests missing.",
                    "recommendation": "revise and re-review", "build_context_received": True,
                }
            else:
                output.result = {
                    "verdict": "PASS", "verdict_reason": "All good",
                    "acceptance_criteria": [
                        {"criterion": "Has tests", "status": "PASS", "notes": "Tests added"},
                        {"criterion": "Has docs", "status": "PASS", "notes": "README present"},
                    ],
                    "automated_checks": [], "findings": [], "policy_compliance": [],
                    "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                    "missing_items": [], "summary": "OK.",
                    "recommendation": "approve", "build_context_received": True,
                }
            return output

        monkeypatch.setattr(BuilderAgent, "execute", capturing_builder)
        monkeypatch.setattr(ReviewerAgent, "execute", reviewer_fail_then_pass)
        pipeline, _ = stub_pipeline
        pipeline.invoke({
            "run_id": "test-rev-002",
            "task_description": "Build something",
            "acceptance_criteria": ["Has tests", "Has docs"],
            "constraints": [],
            "approval_level": 0,
        })

        # builder ran twice: initial + 1 revision
        assert len(captured_contexts) == 2, f"Expected 2 builder calls, got {len(captured_contexts)}"
        initial_ctx = captured_contexts[0]
        revision_ctx = captured_contexts[1]

        assert "revision_feedback" not in initial_ctx, "Initial run must not have revision_feedback"
        assert "revision_feedback" in revision_ctx, "Revision run must have revision_feedback"

        feedback = revision_ctx["revision_feedback"]
        assert feedback["attempt"] == 1
        assert feedback["prior_verdict"] == "FAIL"
        failed = feedback["failed_criteria"]
        assert len(failed) == 1
        assert failed[0]["criterion"] == "Has tests"
        assert failed[0]["status"] == "FAIL"

    def test_retry_exhaustion_produces_escalation_and_needs_revision(self, stub_pipeline, monkeypatch):
        """Permanent FAIL: after _MAX_REVISIONS retries, status is needs_revision + escalation."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent
        from workflows.langgraph.graphs.dispatch_pipeline import _MAX_REVISIONS

        def always_fail(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "verdict": "FAIL",
                "verdict_reason": "Still broken",
                "acceptance_criteria": [
                    {"criterion": "Must work", "status": "FAIL", "notes": "Broken"}
                ],
                "automated_checks": [], "findings": [],
                "policy_compliance": [],
                "plan_adherence": {"matches_plan": "NO", "deviations": "everything"},
                "missing_items": [], "summary": "Broken.",
                "recommendation": "revise and re-review", "build_context_received": True,
            }
            return output

        reviewer_call_count = {"n": 0}
        original_execute = always_fail

        def counting_fail(self, agent_input, output):
            reviewer_call_count["n"] += 1
            return original_execute(self, agent_input, output)

        monkeypatch.setattr(ReviewerAgent, "execute", counting_fail)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-rev-003",
            "task_description": "Build something that keeps failing",
            "acceptance_criteria": ["Must work"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["status"] == "needs_revision"
        assert result["current_stage"] == "done"
        # Reviewer ran: initial + _MAX_REVISIONS retries
        expected_calls = 1 + _MAX_REVISIONS
        assert reviewer_call_count["n"] == expected_calls, (
            f"Expected {expected_calls} reviewer calls, got {reviewer_call_count['n']}"
        )
        # Escalation message present
        escalations = result.get("escalations", [])
        assert any("Revision limit" in e for e in escalations), (
            f"Expected escalation message, got: {escalations}"
        )
        # revision_count reflects all attempts
        assert result["revision_count"] == expected_calls

    def test_no_infinite_loop_pass_with_issues(self, stub_pipeline, monkeypatch):
        """PASS WITH ISSUES must not re-enter the revision loop — routes directly to persist."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent

        call_count = {"n": 0}

        def pass_with_issues(self, agent_input, output):
            call_count["n"] += 1
            output.status = TaskStatus.COMPLETED
            output.result = {
                "verdict": "PASS WITH ISSUES",
                "verdict_reason": "Works but has minor issues",
                "acceptance_criteria": [
                    {"criterion": "Works", "status": "PASS", "notes": "Functional"},
                ],
                "automated_checks": [], "findings": [],
                "policy_compliance": [],
                "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                "missing_items": [], "summary": "Minor issues.",
                "recommendation": "approve", "build_context_received": True,
            }
            return output

        monkeypatch.setattr(ReviewerAgent, "execute", pass_with_issues)
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-rev-004",
            "task_description": "Build something",
            "acceptance_criteria": ["Works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert result["status"] == "completed"
        assert call_count["n"] == 1, (
            f"Reviewer ran {call_count['n']} time(s); PASS WITH ISSUES must not loop"
        )


class TestWorktreeLifecycle:
    """Tests for WorktreeManager and pipeline worktree lifecycle integration."""

    # ── Unit tests for WorktreeManager ──────────────────────────────────────

    def test_worktree_manager_path_convention(self, tmp_path):
        """path() returns {repo_root}/../worktrees/{run_id}."""
        from ai_ops.runtime.worktree import WorktreeManager

        mgr = WorktreeManager(repo_root=tmp_path / "ai-ops")
        result = mgr.path("my-run")
        assert result == tmp_path / "worktrees" / "my-run"

    def test_worktree_manager_branch_name(self, tmp_path):
        """branch_name() uses the ai-ops/run/ prefix convention."""
        from ai_ops.runtime.worktree import WorktreeManager

        mgr = WorktreeManager(repo_root=tmp_path)
        assert mgr.branch_name("smoke-011") == "ai-ops/run/smoke-011"

    def test_worktree_manager_create_calls_git(self, tmp_path, monkeypatch):
        """create() invokes git worktree add with correct branch and path."""
        import subprocess
        from ai_ops.runtime.worktree import WorktreeManager

        calls = []

        def fake_run(cmd, cwd, capture_output, text):
            calls.append(cmd)
            result = type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)
        mgr = WorktreeManager(repo_root=tmp_path)
        wt_path = mgr.create("test-run-01")

        assert any("worktree" in " ".join(c) and "add" in c for c in calls), (
            f"git worktree add not called; calls were: {calls}"
        )
        assert str(wt_path) == str(mgr.path("test-run-01"))
        # Branch name must use the canonical prefix
        add_call = next(c for c in calls if "add" in c)
        assert "ai-ops/run/test-run-01" in add_call

    def test_worktree_manager_create_raises_on_git_failure(self, tmp_path, monkeypatch):
        """create() raises RuntimeError when git worktree add fails."""
        import subprocess
        from ai_ops.runtime.worktree import WorktreeManager

        def fake_run(cmd, cwd, capture_output, text):
            return type("R", (), {"returncode": 1, "stderr": "fatal: already exists", "stdout": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        mgr = WorktreeManager(repo_root=tmp_path)

        with pytest.raises(RuntimeError, match="git worktree add failed"):
            mgr.create("bad-run")

    def test_worktree_manager_destroy_calls_git(self, tmp_path, monkeypatch):
        """destroy() calls git worktree remove and git branch -D."""
        import subprocess
        from ai_ops.runtime.worktree import WorktreeManager

        calls = []

        def fake_run(cmd, cwd, capture_output, text):
            calls.append(cmd)
            return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        mgr = WorktreeManager(repo_root=tmp_path)
        mgr.destroy("test-run-01")

        cmds = [" ".join(c) for c in calls]
        assert any("worktree" in c and "remove" in c for c in cmds), (
            f"git worktree remove not called; commands: {cmds}"
        )
        assert any("branch" in c and "-D" in c for c in cmds), (
            f"git branch -D not called; commands: {cmds}"
        )

    def test_worktree_manager_destroy_is_safe_on_failure(self, tmp_path, monkeypatch):
        """destroy() does not raise even when both git commands fail."""
        import subprocess
        from ai_ops.runtime.worktree import WorktreeManager

        def fake_run(cmd, cwd, capture_output, text):
            return type("R", (), {"returncode": 1, "stderr": "not found", "stdout": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        mgr = WorktreeManager(repo_root=tmp_path)
        mgr.destroy("nonexistent-run")  # must not raise

    def test_worktree_manager_create_removes_stale_path(self, tmp_path, monkeypatch):
        """create() calls destroy() first when the worktree path already exists."""
        import subprocess
        from ai_ops.runtime.worktree import WorktreeManager

        calls = []

        def fake_run(cmd, cwd, capture_output, text):
            calls.append(list(cmd))
            return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        mgr = WorktreeManager(repo_root=tmp_path)

        # Pre-create the path so it looks like a stale worktree
        mgr.path("stale-run").mkdir(parents=True)
        mgr.create("stale-run")

        # destroy() must have been invoked before add (remove appears before add)
        cmds = [" ".join(c) for c in calls]
        remove_idx = next((i for i, c in enumerate(cmds) if "remove" in c), None)
        add_idx = next((i for i, c in enumerate(cmds) if "add" in c), None)
        assert remove_idx is not None, "worktree remove not called for stale path"
        assert add_idx is not None, "worktree add not called after cleanup"
        assert remove_idx < add_idx, "remove must precede add"

    # ── Pipeline integration tests ───────────────────────────────────────────

    def test_init_node_stores_worktree_path_in_state(self, tmp_path):
        """When worktree_manager is provided, init_node stores worktree_path in state."""
        from unittest.mock import MagicMock
        from ai_ops.runtime.worktree import WorktreeManager

        repo_root = tmp_path / "ai-ops"
        (repo_root / "runs" / "active").mkdir(parents=True)
        (repo_root / "runs" / "completed").mkdir(parents=True)
        (repo_root / "runs" / "failed").mkdir(parents=True)
        (repo_root / "memory" / "run-summaries").mkdir(parents=True)

        mock_wm = MagicMock(spec=WorktreeManager)
        expected_path = tmp_path / "worktrees" / "test-wt-init"
        mock_wm.create.return_value = expected_path

        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persistence=RunPersistence(repo_root=repo_root),
            persist_results=True,
            worktree_manager=mock_wm,
        )

        result = pipeline.invoke({
            "run_id": "test-wt-init",
            "task_description": "Build something",
            "acceptance_criteria": ["It works"],
            "constraints": [],
            "approval_level": 0,
        })

        mock_wm.create.assert_called_once_with("test-wt-init")
        assert result.get("worktree_path") == str(expected_path)

    def test_persist_node_destroys_worktree(self, tmp_path):
        """When worktree_manager is provided, persist_node calls destroy."""
        from unittest.mock import MagicMock
        from ai_ops.runtime.worktree import WorktreeManager

        repo_root = tmp_path / "ai-ops"
        (repo_root / "runs" / "active").mkdir(parents=True)
        (repo_root / "runs" / "completed").mkdir(parents=True)
        (repo_root / "runs" / "failed").mkdir(parents=True)
        (repo_root / "memory" / "run-summaries").mkdir(parents=True)

        mock_wm = MagicMock(spec=WorktreeManager)
        mock_wm.create.return_value = tmp_path / "worktrees" / "test-wt-destroy"

        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persistence=RunPersistence(repo_root=repo_root),
            persist_results=True,
            worktree_manager=mock_wm,
        )

        pipeline.invoke({
            "run_id": "test-wt-destroy",
            "task_description": "Build something",
            "acceptance_criteria": ["It works"],
            "constraints": [],
            "approval_level": 0,
        })

        mock_wm.destroy.assert_called_once_with("test-wt-destroy")

    def test_no_worktree_manager_leaves_worktree_path_empty(self, stub_pipeline):
        """When worktree_manager is None (default), worktree_path is empty string."""
        pipeline, _ = stub_pipeline
        result = pipeline.invoke({
            "run_id": "test-wt-none",
            "task_description": "Build something",
            "acceptance_criteria": ["It works"],
            "constraints": [],
            "approval_level": 0,
        })
        assert result.get("worktree_path", "") == ""

    def test_worktree_create_failure_does_not_crash_pipeline(self, tmp_path):
        """A RuntimeError from worktree create is caught; pipeline continues."""
        from unittest.mock import MagicMock
        from ai_ops.runtime.worktree import WorktreeManager

        repo_root = tmp_path / "ai-ops"
        (repo_root / "runs" / "active").mkdir(parents=True)
        (repo_root / "runs" / "completed").mkdir(parents=True)
        (repo_root / "runs" / "failed").mkdir(parents=True)
        (repo_root / "memory" / "run-summaries").mkdir(parents=True)

        mock_wm = MagicMock(spec=WorktreeManager)
        mock_wm.create.side_effect = RuntimeError("git worktree add failed: repo is bare")

        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persistence=RunPersistence(repo_root=repo_root),
            persist_results=True,
            worktree_manager=mock_wm,
        )

        result = pipeline.invoke({
            "run_id": "test-wt-fail",
            "task_description": "Build something",
            "acceptance_criteria": ["It works"],
            "constraints": [],
            "approval_level": 0,
        })

        # Pipeline must complete despite worktree failure
        assert result["current_stage"] == "done"
        assert result.get("worktree_path", "") == ""


class TestFileTools:
    """Unit tests for FileTools — file I/O scoped to a worktree."""

    def test_write_file_creates_file(self, tmp_path):
        """write_file creates the file with correct content."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path)
        written = ft.write_file("hello.py", "print('hi')")

        assert written == tmp_path / "hello.py"
        assert (tmp_path / "hello.py").read_text() == "print('hi')"

    def test_write_file_creates_parent_directories(self, tmp_path):
        """write_file creates intermediate directories."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path)
        ft.write_file("src/utils/math.py", "def add(a, b): return a + b")

        assert (tmp_path / "src" / "utils" / "math.py").exists()

    def test_read_file_returns_content(self, tmp_path):
        """read_file returns the content written by write_file."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path)
        ft.write_file("data.txt", "hello world")
        assert ft.read_file("data.txt") == "hello world"

    def test_read_file_raises_when_missing(self, tmp_path):
        """read_file raises FileNotFoundError for non-existent files."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path)
        with pytest.raises(FileNotFoundError):
            ft.read_file("nonexistent.py")

    def test_list_files_returns_all_files(self, tmp_path):
        """list_files returns all files under the worktree."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path)
        ft.write_file("a.py", "")
        ft.write_file("sub/b.py", "")
        result = ft.list_files()
        assert "a.py" in result
        assert "sub/b.py" in result

    def test_list_files_empty_when_no_files(self, tmp_path):
        """list_files returns empty list when directory is empty."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path)
        assert ft.list_files() == []

    def test_write_file_path_traversal_raises(self, tmp_path):
        """write_file raises ValueError for paths that escape the worktree."""
        from ai_ops.tools.file_tools import FileTools

        ft = FileTools(tmp_path / "worktree")
        (tmp_path / "worktree").mkdir()

        with pytest.raises(ValueError, match="resolves outside worktree"):
            ft.write_file("../../etc/passwd", "malicious")


class TestShellTools:
    """Unit tests for ShellTools — shell execution scoped to a worktree."""

    def test_shell_result_passed_property(self):
        """ShellResult.passed returns True only for returncode 0."""
        from ai_ops.tools.shell_tools import ShellResult

        assert ShellResult(returncode=0, stdout="ok", stderr="").passed is True
        assert ShellResult(returncode=1, stdout="", stderr="err").passed is False

    def test_shell_result_status_property(self):
        """ShellResult.status returns 'PASS' or 'FAIL' based on returncode."""
        from ai_ops.tools.shell_tools import ShellResult

        assert ShellResult(returncode=0, stdout="", stderr="").status == "PASS"
        assert ShellResult(returncode=2, stdout="", stderr="").status == "FAIL"

    def test_run_command_returns_shell_result(self, tmp_path, monkeypatch):
        """run_command returns a ShellResult with correct fields."""
        import subprocess
        from ai_ops.tools.shell_tools import ShellTools

        def fake_run(cmd, cwd, capture_output, text, timeout):
            return type("R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        shell = ShellTools(tmp_path)
        result = shell.run_command(["echo", "ok"])

        assert result.returncode == 0
        assert result.stdout == "ok\n"
        assert result.passed is True

    def test_run_ruff_uses_python_module(self, tmp_path, monkeypatch):
        """run_ruff calls ruff via sys.executable -m ruff check."""
        import subprocess
        import sys
        from ai_ops.tools.shell_tools import ShellTools

        captured = []

        def fake_run(cmd, cwd, capture_output, text, timeout):
            captured.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        shell = ShellTools(tmp_path)
        shell.run_ruff()

        assert captured, "subprocess.run not called"
        cmd = captured[0]
        assert cmd[0] == sys.executable
        assert "ruff" in cmd
        assert "check" in cmd

    def test_run_pytest_uses_python_module(self, tmp_path, monkeypatch):
        """run_pytest calls pytest via sys.executable -m pytest."""
        import subprocess
        import sys
        from ai_ops.tools.shell_tools import ShellTools

        captured = []

        def fake_run(cmd, cwd, capture_output, text, timeout):
            captured.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        ShellTools(tmp_path).run_pytest()

        cmd = captured[0]
        assert cmd[0] == sys.executable
        assert "pytest" in cmd

    def test_run_command_on_timeout_returns_fail_result(self, tmp_path, monkeypatch):
        """run_command returns a FAIL ShellResult when the command times out."""
        import subprocess
        from ai_ops.tools.shell_tools import ShellTools

        def fake_run(cmd, cwd, capture_output, text, timeout):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = ShellTools(tmp_path).run_command(["sleep", "9999"], timeout=1)

        assert result.returncode == 1
        assert "timed out" in result.stderr.lower()


class TestBuilderFileWriting:
    """Tests for builder writing code_output to the worktree."""

    def test_builder_writes_code_output_files(self, tmp_path, monkeypatch):
        """Builder writes each key in code_output to the worktree when path is available."""
        from unittest.mock import MagicMock
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent
        from ai_ops.runtime.worktree import WorktreeManager

        worktree = tmp_path / "wt"
        worktree.mkdir()

        # Patch _execute_stub so it returns code_output; execute() then writes the files
        def fake_stub(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "implementation_summary": "Built add function",
                "code_output": {"src/math.py": "def add(a, b): return a + b\n"},
                "files_changed": {"created": ["src/math.py"], "modified": [], "deleted": []},
                "tests_created": [], "dependencies_added": [],
                "deviations_from_plan": "none", "known_limitations": [],
            }
            return output

        monkeypatch.setattr(BuilderAgent, "_execute_stub", fake_stub)

        # Use a pipeline with a mock WorktreeManager so worktree_path flows into state
        repo_root = tmp_path / "ai-ops"
        (repo_root / "runs" / "active").mkdir(parents=True)
        (repo_root / "runs" / "completed").mkdir(parents=True)
        (repo_root / "runs" / "failed").mkdir(parents=True)
        (repo_root / "memory" / "run-summaries").mkdir(parents=True)

        mock_wm = MagicMock(spec=WorktreeManager)
        mock_wm.create.return_value = worktree

        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persistence=RunPersistence(repo_root=repo_root),
            persist_results=True,
            worktree_manager=mock_wm,
        )
        pipeline.invoke({
            "run_id": "test-bfw-001",
            "task_description": "Build add function",
            "acceptance_criteria": ["add works"],
            "constraints": [],
            "approval_level": 0,
        })

        written_file = worktree / "src" / "math.py"
        assert written_file.exists(), "Builder did not write src/math.py to worktree"
        assert "def add" in written_file.read_text()

    def test_builder_records_files_written_in_output(self, tmp_path, monkeypatch):
        """files_written key is added to builder output after successful writes."""
        from unittest.mock import MagicMock
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent
        from ai_ops.runtime.worktree import WorktreeManager

        worktree = tmp_path / "wt2"
        worktree.mkdir()

        def fake_stub(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "implementation_summary": "Built something",
                "code_output": {"module.py": "x = 1\n"},
                "files_changed": {"created": ["module.py"], "modified": [], "deleted": []},
                "tests_created": [], "dependencies_added": [],
                "deviations_from_plan": "none", "known_limitations": [],
            }
            return output

        monkeypatch.setattr(BuilderAgent, "_execute_stub", fake_stub)

        repo_root = tmp_path / "ai-ops"
        (repo_root / "runs" / "active").mkdir(parents=True)
        (repo_root / "runs" / "completed").mkdir(parents=True)
        (repo_root / "runs" / "failed").mkdir(parents=True)
        (repo_root / "memory" / "run-summaries").mkdir(parents=True)

        mock_wm = MagicMock(spec=WorktreeManager)
        mock_wm.create.return_value = worktree

        pipeline = create_pipeline(
            llm_client=StubClient(),
            approval_handler=AutoApprovalHandler(),
            persistence=RunPersistence(repo_root=repo_root),
            persist_results=True,
            worktree_manager=mock_wm,
        )
        result = pipeline.invoke({
            "run_id": "test-bfw-002",
            "task_description": "Build something",
            "acceptance_criteria": ["works"],
            "constraints": [],
            "approval_level": 0,
        })

        builder_out = result.get("builder_output", {})
        assert "files_written" in builder_out, "files_written not in builder_output"
        assert "module.py" in builder_out["files_written"]

    def test_builder_no_file_writes_without_worktree_path(self, stub_pipeline, monkeypatch):
        """When worktree_path is empty, code_output is not acted on (no file write attempt)."""
        from ai_ops.agents.base import TaskStatus
        from ai_ops.agents.builder import BuilderAgent
        from ai_ops.tools.file_tools import FileTools

        write_called = {"n": 0}
        original_write = FileTools.write_file

        def tracking_write(self, *args, **kwargs):
            write_called["n"] += 1
            return original_write(self, *args, **kwargs)

        monkeypatch.setattr(FileTools, "write_file", tracking_write)

        def fake_stub(self, agent_input, output):
            output.status = TaskStatus.COMPLETED
            output.result = {
                "implementation_summary": "Built",
                "code_output": {"file.py": "x = 1"},
                "files_changed": {"created": [], "modified": [], "deleted": []},
                "tests_created": [], "dependencies_added": [],
                "deviations_from_plan": "none", "known_limitations": [],
            }
            return output

        monkeypatch.setattr(BuilderAgent, "_execute_stub", fake_stub)

        pipeline, _ = stub_pipeline  # worktree_manager=None → worktree_path=""
        pipeline.invoke({
            "run_id": "test-bfw-003",
            "task_description": "Build",
            "acceptance_criteria": ["works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert write_called["n"] == 0, "FileTools.write_file called when no worktree_path"


class TestReviewerShellTools:
    """Tests for reviewer running automated checks against the worktree."""

    def test_reviewer_runs_checks_when_worktree_has_python_files(
        self, tmp_path, monkeypatch
    ):
        """When worktree has .py files, _execute_llm calls ruff/mypy/pytest."""
        import json
        from ai_ops.agents.base import AgentInput, AgentOutput, TaskStatus
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "foo.py").write_text("x = 1\n")

        check_calls: list[str] = []

        monkeypatch.setattr(ShellTools, "run_ruff",
            lambda self, paths=None: (check_calls.append("ruff") or ShellResult(0, "ok", "")))
        monkeypatch.setattr(ShellTools, "run_mypy",
            lambda self, paths=None: (check_calls.append("mypy") or ShellResult(0, "ok", "")))
        monkeypatch.setattr(ShellTools, "run_pytest",
            lambda self, paths=None: (check_calls.append("pytest") or ShellResult(0, "1 passed", "")))

        # Use a non-stub client so _execute_llm is called, not _execute_stub
        class _MockLLMClient:
            provider_name = "mock"
            model_name = "mock"
            def complete(self, system, user, expect_json=True):
                return json.dumps({
                    "verdict": "PASS",
                    "verdict_reason": "All good",
                    "acceptance_criteria": [{"criterion": "works", "status": "PASS", "notes": ""}],
                    "automated_checks": [],
                    "findings": [],
                    "policy_compliance": [],
                    "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                    "missing_items": [],
                    "summary": "Looks good.",
                    "recommendation": "approve",
                    "build_context_received": False,
                })

        agent = ReviewerAgent(llm_client=_MockLLMClient())
        agent_input = AgentInput(
            run_id="test-rst-001",
            description="Review it",
            acceptance_criteria=["works"],
            context={
                "worktree_path": str(worktree),
                # files_written is required to scope checks to the deliverable
                "build_output": {"files_written": ["foo.py"]},
            },
        )
        output = AgentOutput(task_id="t1", agent_role="reviewer")
        agent._execute_llm(agent_input, output)

        assert "ruff" in check_calls, "ruff not run"
        assert "mypy" in check_calls, "mypy not run"
        # foo.py is not a test file so pytest should be skipped
        assert "pytest" not in check_calls, "pytest should not run for non-test files"

    def test_reviewer_passes_check_results_to_llm_context(
        self, tmp_path, monkeypatch
    ):
        """automated_checks_results is injected into enriched_input before LLM call."""
        import json
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt2"
        worktree.mkdir()
        (worktree / "app.py").write_text("x = 1\n")

        monkeypatch.setattr(ShellTools, "run_ruff",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_mypy",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_pytest",
            lambda self, paths=None: ShellResult(0, "1 passed", ""))

        captured_user_msg: list[str] = []

        class _CapturingLLMClient:
            provider_name = "mock"
            model_name = "mock"
            def complete(self, system, user, expect_json=True):
                captured_user_msg.append(user)
                return json.dumps({
                    "verdict": "PASS", "verdict_reason": "ok",
                    "acceptance_criteria": [],
                    "automated_checks": [], "findings": [],
                    "policy_compliance": [],
                    "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
                    "missing_items": [], "summary": "ok.",
                    "recommendation": "approve", "build_context_received": False,
                })

        agent = ReviewerAgent(llm_client=_CapturingLLMClient())
        agent_input = AgentInput(
            run_id="test-rst-002",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {"files_written": ["app.py"]},
            },
        )
        from ai_ops.agents.base import AgentOutput
        agent._execute_llm(agent_input, AgentOutput(task_id="t2", agent_role="reviewer"))

        assert captured_user_msg, "LLM complete() not called"
        # automated_checks_results should appear in the user message sent to LLM
        assert "automated_checks_results" in captured_user_msg[0], (
            "automated_checks_results not in LLM user message"
        )

    def test_reviewer_skips_checks_when_no_worktree_path(self, stub_pipeline, monkeypatch):
        """Reviewer does not call ShellTools when worktree_path is empty."""
        from ai_ops.tools.shell_tools import ShellTools

        check_called = {"n": 0}
        original_run = ShellTools.run_command
        def tracking_run(self, *args, **kwargs):
            check_called["n"] += 1
            return original_run(self, *args, **kwargs)
        monkeypatch.setattr(ShellTools, "run_command", tracking_run)

        pipeline, _ = stub_pipeline  # worktree_manager=None → worktree_path=""
        pipeline.invoke({
            "run_id": "test-rst-003",
            "task_description": "Build",
            "acceptance_criteria": ["works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert check_called["n"] == 0, "ShellTools called when no worktree_path"

    def test_reviewer_skips_checks_when_worktree_has_no_python_files(
        self, stub_pipeline, tmp_path, monkeypatch
    ):
        """Reviewer skips tool runs when the worktree contains no .py files."""
        from ai_ops.tools.shell_tools import ShellTools

        empty_worktree = tmp_path / "empty"
        empty_worktree.mkdir()

        check_called = {"n": 0}
        original_run = ShellTools.run_command
        def tracking_run(self, *args, **kwargs):
            check_called["n"] += 1
            return original_run(self, *args, **kwargs)
        monkeypatch.setattr(ShellTools, "run_command", tracking_run)

        from workflows.langgraph.graphs import dispatch_pipeline as dp
        original_init = dp.init_node
        def patched_init(state):
            result = original_init(state)
            result["worktree_path"] = str(empty_worktree)
            return result
        monkeypatch.setattr(dp, "init_node", patched_init)

        pipeline, _ = stub_pipeline
        pipeline.invoke({
            "run_id": "test-rst-004",
            "task_description": "Build",
            "acceptance_criteria": ["works"],
            "constraints": [],
            "approval_level": 0,
        })

        assert check_called["n"] == 0, "ShellTools called on empty worktree"


class TestReviewerCheckScope:
    """Tests verifying that automated checks target only files_written, not the full repo."""

    def _mock_llm_response(self) -> str:
        import json
        return json.dumps({
            "verdict": "PASS", "verdict_reason": "ok",
            "acceptance_criteria": [],
            "automated_checks": [], "findings": [],
            "policy_compliance": [],
            "plan_adherence": {"matches_plan": "YES", "deviations": "none"},
            "missing_items": [], "summary": "ok.", "recommendation": "approve",
            "build_context_received": True,
        })

    def _mock_llm_client(self, response: str):
        class _Client:
            provider_name = "mock"
            model_name = "mock"
            def complete(self, system, user, expect_json=True):
                return response
        return _Client()

    def test_ruff_called_with_files_written_not_dot(self, tmp_path, monkeypatch):
        """ruff receives the specific files from files_written, not '.'."""
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "add.py").write_text("def add(a,b): return a+b\n")

        ruff_targets: list = []
        monkeypatch.setattr(ShellTools, "run_ruff",
            lambda self, paths=None: (ruff_targets.append(paths) or ShellResult(0, "ok", "")))
        monkeypatch.setattr(ShellTools, "run_mypy",
            lambda self, paths=None: ShellResult(0, "ok", ""))

        agent = ReviewerAgent(llm_client=self._mock_llm_client(self._mock_llm_response()))
        agent_input = AgentInput(
            run_id="scope-001",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {"files_written": ["add.py"]},
            },
        )
        agent._execute_llm(agent_input, AgentOutput(task_id="s1", agent_role="reviewer"))

        assert ruff_targets, "run_ruff not called"
        targets_used = ruff_targets[0]
        assert targets_used == ["add.py"], (
            f"ruff should target ['add.py'], got {targets_used!r}"
        )
        assert "." not in (targets_used or []), "ruff must not target '.' (full worktree)"

    def test_mypy_called_with_files_written_not_dot(self, tmp_path, monkeypatch):
        """mypy receives the specific files from files_written, not '.'."""
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "module.py").write_text("x: int = 1\n")
        (worktree / "helper.py").write_text("y: str = 'a'\n")

        mypy_targets: list = []
        monkeypatch.setattr(ShellTools, "run_ruff",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_mypy",
            lambda self, paths=None: (mypy_targets.append(paths) or ShellResult(0, "ok", "")))

        agent = ReviewerAgent(llm_client=self._mock_llm_client(self._mock_llm_response()))
        agent_input = AgentInput(
            run_id="scope-002",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {"files_written": ["module.py", "helper.py"]},
            },
        )
        agent._execute_llm(agent_input, AgentOutput(task_id="s2", agent_role="reviewer"))

        assert mypy_targets, "run_mypy not called"
        targets_used = sorted(mypy_targets[0])
        assert targets_used == ["helper.py", "module.py"], (
            f"mypy targets should be the two written files, got {targets_used!r}"
        )

    def test_pytest_runs_on_test_files_only(self, tmp_path, monkeypatch):
        """pytest targets only test files from files_written."""
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "add.py").write_text("def add(a,b): return a+b\n")
        (worktree / "test_add.py").write_text("from add import add\ndef test_it(): assert add(1,2)==3\n")

        pytest_targets: list = []
        monkeypatch.setattr(ShellTools, "run_ruff",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_mypy",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_pytest",
            lambda self, paths=None: (pytest_targets.append(paths) or ShellResult(0, "1 passed", "")))

        agent = ReviewerAgent(llm_client=self._mock_llm_client(self._mock_llm_response()))
        agent_input = AgentInput(
            run_id="scope-003",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {"files_written": ["add.py", "test_add.py"]},
            },
        )
        agent._execute_llm(agent_input, AgentOutput(task_id="s3", agent_role="reviewer"))

        assert pytest_targets, "run_pytest not called when test files present"
        assert pytest_targets[0] == ["test_add.py"], (
            f"pytest should target only test files, got {pytest_targets[0]!r}"
        )

    def test_pytest_skipped_when_no_test_files_in_files_written(self, tmp_path, monkeypatch):
        """pytest is not run when files_written contains no test files."""
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "utils.py").write_text("def helper(): pass\n")

        pytest_called = {"n": 0}
        monkeypatch.setattr(ShellTools, "run_ruff",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_mypy",
            lambda self, paths=None: ShellResult(0, "ok", ""))
        monkeypatch.setattr(ShellTools, "run_pytest",
            lambda self, paths=None: (pytest_called.update({"n": pytest_called["n"] + 1}) or ShellResult(0, "", "")))

        agent = ReviewerAgent(llm_client=self._mock_llm_client(self._mock_llm_response()))
        agent_input = AgentInput(
            run_id="scope-004",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {"files_written": ["utils.py"]},
            },
        )
        agent._execute_llm(agent_input, AgentOutput(task_id="s4", agent_role="reviewer"))

        assert pytest_called["n"] == 0, "pytest called when no test files in files_written"

    def test_checks_skipped_when_no_files_written(self, tmp_path, monkeypatch):
        """All checks are skipped when build_output has no files_written."""
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "existing.py").write_text("x = 1\n")  # pre-existing file

        check_called = {"n": 0}
        original_run = ShellTools.run_command
        def tracking_run(self, *args, **kwargs):
            check_called["n"] += 1
            return original_run(self, *args, **kwargs)
        monkeypatch.setattr(ShellTools, "run_command", tracking_run)

        agent = ReviewerAgent(llm_client=self._mock_llm_client(self._mock_llm_response()))
        agent_input = AgentInput(
            run_id="scope-005",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {},  # no files_written key
            },
        )
        agent._execute_llm(agent_input, AgentOutput(task_id="s5", agent_role="reviewer"))

        assert check_called["n"] == 0, (
            "ShellTools called despite no files_written — would scan full worktree"
        )

    def test_checks_skipped_when_files_written_empty(self, tmp_path, monkeypatch):
        """All checks are skipped when files_written is an empty list."""
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools

        worktree = tmp_path / "wt"
        worktree.mkdir()

        check_called = {"n": 0}
        original_run = ShellTools.run_command
        def tracking_run(self, *args, **kwargs):
            check_called["n"] += 1
            return original_run(self, *args, **kwargs)
        monkeypatch.setattr(ShellTools, "run_command", tracking_run)

        agent = ReviewerAgent(llm_client=self._mock_llm_client(self._mock_llm_response()))
        agent_input = AgentInput(
            run_id="scope-006",
            description="Review",
            acceptance_criteria=[],
            context={
                "worktree_path": str(worktree),
                "build_output": {"files_written": []},
            },
        )
        agent._execute_llm(agent_input, AgentOutput(task_id="s6", agent_role="reviewer"))

        assert check_called["n"] == 0, "ShellTools called when files_written is empty"


# ===========================================================================
# TestLLMClientToolCall
# ===========================================================================


class TestLLMClientToolCall:
    """Tests for AnthropicClient.complete_with_tools loop logic."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_text_block(text: str):
        from unittest.mock import MagicMock
        b = MagicMock()
        b.type = "text"
        b.text = text
        return b

    @staticmethod
    def _make_tool_use_block(name: str, inputs: dict, block_id: str = "tu_001"):
        from unittest.mock import MagicMock
        b = MagicMock()
        b.type = "tool_use"
        b.id = block_id
        b.name = name
        b.input = inputs
        return b

    @staticmethod
    def _make_response(content, stop_reason: str):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.content = content
        r.stop_reason = stop_reason
        r.model = "claude-test"
        r.usage.input_tokens = 10
        r.usage.output_tokens = 20
        return r

    def _make_client(self, side_effects: list):
        """Create AnthropicClient whose messages.create returns from side_effects list."""
        from unittest.mock import MagicMock, patch
        from ai_ops.llm.client import AnthropicClient

        call_idx = [0]

        def mock_create(**kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            return side_effects[idx]

        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_inst = MagicMock()
            MockAnthropic.return_value = mock_inst
            mock_inst.messages.create.side_effect = mock_create
            client = AnthropicClient(api_key="test-key")
        # mock_inst persists via client._client reference
        return client, mock_inst

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_terminates_on_end_turn_no_tools(self):
        """Loop returns after first call when stop_reason is end_turn with no tool_use."""
        response = self._make_response(
            [self._make_text_block('{"implementation_summary": "done"}')],
            stop_reason="end_turn",
        )
        client, mock_inst = self._make_client([response])

        executed = []
        final_text, log = client.complete_with_tools(
            system="sys",
            user="user",
            tools=[],
            tool_executor=lambda n, i: executed.append(n) or "ok",
        )

        assert '{"implementation_summary": "done"}' in final_text
        assert log == []
        assert executed == []
        assert mock_inst.messages.create.call_count == 1

    def test_terminates_when_no_tool_use_blocks_in_response(self):
        """Loop returns when response has no tool_use blocks, even if stop_reason is tool_use."""
        response = self._make_response(
            [self._make_text_block("final answer")],
            stop_reason="tool_use",
        )
        client, mock_inst = self._make_client([response])

        final_text, log = client.complete_with_tools(
            system="sys", user="user", tools=[], tool_executor=lambda n, i: "ok"
        )

        assert final_text == "final answer"
        assert log == []
        assert mock_inst.messages.create.call_count == 1

    def test_executes_tool_and_sends_result_back(self):
        """Tool executor is called; result is fed back in the next API call."""
        tool_response = self._make_response(
            [self._make_tool_use_block("write_file", {"path": "x.py", "content": "x=1"})],
            stop_reason="tool_use",
        )
        end_response = self._make_response(
            [self._make_text_block('{"implementation_summary": "wrote x.py"}')],
            stop_reason="end_turn",
        )
        client, mock_inst = self._make_client([tool_response, end_response])

        executed = []

        def executor(name, inputs):
            executed.append((name, inputs))
            return f"wrote {inputs['path']}"

        final_text, log = client.complete_with_tools(
            system="sys",
            user="user",
            tools=[{"name": "write_file"}],
            tool_executor=executor,
        )

        assert executed == [("write_file", {"path": "x.py", "content": "x=1"})]
        assert len(log) == 1
        assert log[0]["tool"] == "write_file"
        assert log[0]["result"] == "wrote x.py"
        assert mock_inst.messages.create.call_count == 2

        # Second call should include the tool_result in messages
        second_call_messages = mock_inst.messages.create.call_args_list[1][1]["messages"]
        user_turn = second_call_messages[-1]
        assert user_turn["role"] == "user"
        assert any(
            b.get("type") == "tool_result" for b in user_turn["content"]
        ), "tool_result not found in second call messages"

    def test_terminates_at_iteration_cap(self):
        """Loop stops after max_iterations even if LLM keeps calling tools."""
        always_tool = self._make_response(
            [self._make_tool_use_block("write_file", {"path": "f.py", "content": "x=1"})],
            stop_reason="tool_use",
        )
        # Provide more responses than the cap so we don't run out
        client, mock_inst = self._make_client([always_tool] * 20)

        call_count = [0]

        def executor(name, inputs):
            call_count[0] += 1
            return "ok"

        client.complete_with_tools(
            system="sys",
            user="user",
            tools=[{"name": "write_file"}],
            tool_executor=executor,
            max_iterations=3,
        )

        # max_iterations=3 → at most 3 API calls
        assert mock_inst.messages.create.call_count <= 3

    def test_tool_executor_error_does_not_crash_loop(self):
        """If the tool executor raises, the loop continues with an error result."""
        tool_response = self._make_response(
            [self._make_tool_use_block("bad_tool", {})],
            stop_reason="tool_use",
        )
        end_response = self._make_response(
            [self._make_text_block('{"implementation_summary": "recovered"}')],
            stop_reason="end_turn",
        )
        client, mock_inst = self._make_client([tool_response, end_response])

        def bad_executor(name, inputs):
            raise ValueError("tool exploded")

        final_text, log = client.complete_with_tools(
            system="sys",
            user="user",
            tools=[],
            tool_executor=bad_executor,
        )

        assert len(log) == 1
        assert "error" in log[0]
        assert mock_inst.messages.create.call_count == 2


# ===========================================================================
# TestParseJsonResponse
# ===========================================================================


class TestParseJsonResponse:
    """Tests for BaseAgent.parse_json_response — all three extraction paths."""

    @staticmethod
    def _agent():
        from ai_ops.agents.builder import BuilderAgent
        from ai_ops.llm.client import StubClient

        return BuilderAgent(llm_client=StubClient())

    def test_pure_json(self):
        """Pure JSON string parses without any extraction needed."""
        result = self._agent().parse_json_response('{"key": "val", "n": 1}')
        assert result == {"key": "val", "n": 1}

    def test_markdown_fence_json(self):
        """JSON wrapped in markdown fences is stripped and parsed."""
        fenced = "```json\n{\"key\": \"val\"}\n```"
        result = self._agent().parse_json_response(fenced)
        assert result == {"key": "val"}

    def test_markdown_fence_no_language_tag(self):
        """Plain ``` fences (no 'json' tag) are also stripped."""
        fenced = "```\n{\"key\": \"val\"}\n```"
        result = self._agent().parse_json_response(fenced)
        assert result == {"key": "val"}

    def test_prose_prefix_single_line_json(self):
        """JSON preceded by prose is extracted and parsed correctly."""
        text = 'Here is the summary:\n\n{"key": "val"}'
        result = self._agent().parse_json_response(text)
        assert result == {"key": "val"}

    def test_prose_prefix_multiline_json(self):
        """Multi-key JSON after prose prefix — mirrors smoke-024 failure pattern."""
        text = (
            "Perfect! I have completed the task. Let me provide the JSON summary:\n\n"
            '{"implementation_summary": "Done", "files_written": ["a.py"], "known_limitations": []}'
        )
        result = self._agent().parse_json_response(text)
        assert result["implementation_summary"] == "Done"
        assert result["files_written"] == ["a.py"]
        assert result["known_limitations"] == []

    def test_empty_string_raises(self):
        """Empty string raises JSONDecodeError."""
        import json

        with pytest.raises(json.JSONDecodeError):
            self._agent().parse_json_response("")

    def test_pure_prose_no_json_raises(self):
        """Pure prose with no JSON object raises JSONDecodeError."""
        import json

        with pytest.raises(json.JSONDecodeError):
            self._agent().parse_json_response("No JSON here at all.")


# ===========================================================================
# TestBuilderToolLoop
# ===========================================================================


class TestBuilderToolLoop:
    """Tests for BuilderAgent tool-call loop (LLM mode with worktree)."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_tool_client(tool_calls: list[tuple[str, dict]], final_json: str):
        """
        Return a fake LLM client that:
        - has complete_with_tools: executes tool_calls then returns final_json
        - has complete (fallback): returns final_json directly
        """

        class _FakeToolClient:
            provider_name = "fake"
            model_name = "fake-tool-v1"

            def complete_with_tools(
                self_inner, system, user, tools, tool_executor, max_iterations=10
            ):
                log = []
                for name, inputs in tool_calls:
                    result = tool_executor(name, inputs)
                    log.append({"tool": name, "input": inputs, "result": result})
                return final_json, log

            def complete(self_inner, system, user, expect_json=False):
                return final_json

        return _FakeToolClient()

    @staticmethod
    def _make_oneshot_client(response_json: str):
        """Fake client with complete() only (no complete_with_tools)."""

        class _FakeOneshotClient:
            provider_name = "fake"
            model_name = "fake-oneshot-v1"

            def complete(self_inner, system, user, expect_json=False):
                return response_json

        return _FakeOneshotClient()

    @staticmethod
    def _make_agent_input(worktree_path: str = "", run_id: str = "loop-test") -> "AgentInput":
        from ai_ops.agents.base import AgentInput

        return AgentInput(
            run_id=run_id,
            description="Implement add(a, b)",
            acceptance_criteria=["add works"],
            context={"worktree_path": worktree_path},
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_routes_to_tool_loop_when_worktree_and_tool_client(self, tmp_path):
        """_execute_llm calls complete_with_tools when worktree_path set and client supports it."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.builder import BuilderAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        final_json = '{"implementation_summary": "wrote files", "files_changed": {"created": [], "modified": [], "deleted": []}, "tests_created": [], "dependencies_added": [], "deviations_from_plan": "none", "known_limitations": []}'
        calls_log = []

        class _TrackingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=10):
                calls_log.append("complete_with_tools")
                return final_json, []

            def complete(self_inner, system, user, expect_json=False):
                calls_log.append("complete")
                return final_json

        agent = BuilderAgent(llm_client=_TrackingClient())
        agent_input = self._make_agent_input(worktree_path=str(worktree))
        agent._execute_llm(agent_input, AgentOutput(task_id="t1", agent_role="builder"))

        assert "complete_with_tools" in calls_log, "complete_with_tools was not called"
        assert "complete" not in calls_log, "complete() was called instead of complete_with_tools"

    def test_files_written_populated_from_write_file_tool_calls(self, tmp_path):
        """files_written in output reflects paths passed to write_file tool calls."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.builder import BuilderAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "pkg").mkdir()

        tool_calls = [
            ("write_file", {"path": "pkg/__init__.py", "content": ""}),
            ("write_file", {"path": "pkg/add.py", "content": "def add(a, b): return a + b\n"}),
            ("write_file", {"path": "tests/test_add.py", "content": "from pkg.add import add\ndef test_add(): assert add(1,2)==3\n"}),
        ]
        final_json = '{"implementation_summary": "done", "files_changed": {"created": [], "modified": [], "deleted": []}, "tests_created": [], "dependencies_added": [], "deviations_from_plan": "none", "known_limitations": []}'

        agent = BuilderAgent(llm_client=self._make_tool_client(tool_calls, final_json))
        agent_input = self._make_agent_input(worktree_path=str(worktree), run_id="loop-fw-001")
        output = agent._execute_llm(
            agent_input, AgentOutput(task_id="t2", agent_role="builder")
        )

        assert output.result.get("files_written") == [
            "pkg/__init__.py",
            "pkg/add.py",
            "tests/test_add.py",
        ], f"Unexpected files_written: {output.result.get('files_written')}"

    def test_files_exist_on_disk_after_tool_loop(self, tmp_path):
        """Files named in write_file calls are physically written to the worktree."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.builder import BuilderAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        tool_calls = [
            ("write_file", {"path": "hello.py", "content": "print('hello')\n"}),
        ]
        final_json = '{"implementation_summary": "done", "files_changed": {"created": [], "modified": [], "deleted": []}, "tests_created": [], "dependencies_added": [], "deviations_from_plan": "none", "known_limitations": []}'

        agent = BuilderAgent(llm_client=self._make_tool_client(tool_calls, final_json))
        agent_input = self._make_agent_input(worktree_path=str(worktree), run_id="loop-disk-001")
        agent._execute_llm(agent_input, AgentOutput(task_id="t3", agent_role="builder"))

        assert (worktree / "hello.py").exists(), "hello.py not found on disk"
        assert "print('hello')" in (worktree / "hello.py").read_text()

    def test_falls_back_to_oneshot_without_worktree(self):
        """Without worktree_path, _execute_llm uses complete() not complete_with_tools."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.builder import BuilderAgent

        calls_log = []

        class _TrackingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=10):
                calls_log.append("complete_with_tools")
                return "{}", []

            def complete(self_inner, system, user, expect_json=False):
                calls_log.append("complete")
                return '{"implementation_summary": "oneshot", "files_changed": {"created": [], "modified": [], "deleted": []}, "tests_created": [], "dependencies_added": [], "deviations_from_plan": "none", "known_limitations": []}'

        agent = BuilderAgent(llm_client=_TrackingClient())
        agent_input = self._make_agent_input(worktree_path="")  # no worktree
        agent._execute_llm(agent_input, AgentOutput(task_id="t4", agent_role="builder"))

        assert "complete" in calls_log, "complete() not called for oneshot fallback"
        assert "complete_with_tools" not in calls_log, "complete_with_tools called without worktree"

    def test_falls_back_to_oneshot_when_client_lacks_tool_support(self, tmp_path):
        """When client has no complete_with_tools, _execute_llm falls back to complete()."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.builder import BuilderAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        calls_log = []

        class _NoToolClient:
            provider_name = "fake"
            model_name = "fake"

            def complete(self_inner, system, user, expect_json=False):
                calls_log.append("complete")
                return '{"implementation_summary": "oneshot", "files_changed": {"created": [], "modified": [], "deleted": []}, "tests_created": [], "dependencies_added": [], "deviations_from_plan": "none", "known_limitations": []}'

        agent = BuilderAgent(llm_client=_NoToolClient())
        agent_input = self._make_agent_input(worktree_path=str(worktree))
        agent._execute_llm(agent_input, AgentOutput(task_id="t5", agent_role="builder"))

        assert "complete" in calls_log, "complete() not called when client lacks tool support"
        assert not hasattr(_NoToolClient(), "complete_with_tools")

    def test_tool_loop_with_prose_wrapped_final_response(self, tmp_path):
        """Builder tool loop succeeds when model wraps final JSON in prose (smoke-024 pattern).

        The model wrote all files via tool calls but its final message was:
        'Perfect! I have completed the task. Let me provide the JSON summary:\\n\\n{...}'
        Before the fix this caused a JSON parse error; after the fix it must parse cleanly.
        """
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.builder import BuilderAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        tool_calls = [
            ("write_file", {"path": "stack_ops/__init__.py", "content": ""}),
            ("write_file", {"path": "stack_ops/stack.py", "content": "class Stack: pass\n"}),
            ("write_file", {"path": "tests/test_stack.py", "content": "from stack_ops.stack import Stack\ndef test_stack(): assert Stack()\n"}),
        ]
        # Simulate the prose-prefix pattern observed in smoke-024
        inner_json = (
            '{"implementation_summary": "Implemented Stack with push/pop/peek/is_empty",'
            ' "files_changed": {"created": ["stack_ops/__init__.py", "stack_ops/stack.py", "tests/test_stack.py"], "modified": [], "deleted": []},'
            ' "tests_created": ["tests/test_stack.py"],'
            ' "dependencies_added": [],'
            ' "deviations_from_plan": "none",'
            ' "known_limitations": []}'
        )
        prose_wrapped = (
            "Perfect! I have successfully implemented the Stack class. "
            "Let me provide the final JSON summary:\n\n" + inner_json
        )

        agent = BuilderAgent(llm_client=self._make_tool_client(tool_calls, prose_wrapped))
        agent_input = self._make_agent_input(worktree_path=str(worktree), run_id="loop-prose-001")
        output = agent._execute_llm(
            agent_input, AgentOutput(task_id="t6", agent_role="builder")
        )

        # JSON must have parsed — implementation_summary from inside the JSON, not the prose blob
        assert output.result.get("implementation_summary") == "Implemented Stack with push/pop/peek/is_empty", (
            f"implementation_summary was not extracted from JSON: {output.result.get('implementation_summary')!r}"
        )
        # No parse error should appear in known_limitations
        limitations = output.result.get("known_limitations", [])
        parse_errors = [x for x in limitations if "JSON parse error" in str(x)]
        assert not parse_errors, f"Unexpected JSON parse error in known_limitations: {parse_errors}"
        # files_written populated from tool calls
        assert output.result.get("files_written") == [
            "stack_ops/__init__.py",
            "stack_ops/stack.py",
            "tests/test_stack.py",
        ]


# ===========================================================================
# TestBuilderPlaceholderEscalation
# ===========================================================================


class TestBuilderPlaceholderEscalation:
    """Tests that the Builder escalates without writing files on placeholder descriptions."""

    @staticmethod
    def _run_builder(description: str, worktree_path: str = "") -> "AgentOutput":
        from ai_ops.agents.base import AgentInput, AgentOutput
        from ai_ops.agents.builder import BuilderAgent
        from ai_ops.llm.client import StubClient

        agent = BuilderAgent(llm_client=StubClient())
        agent_input = AgentInput(
            run_id="esc-test",
            description=description,
            acceptance_criteria=["works"],
            context={"worktree_path": worktree_path},
        )
        return agent.run(agent_input)

    # ------------------------------------------------------------------
    # _is_placeholder_description unit tests
    # ------------------------------------------------------------------

    def test_empty_description_is_placeholder(self):
        from ai_ops.agents.builder import BuilderAgent
        assert BuilderAgent._is_placeholder_description("") is True
        assert BuilderAgent._is_placeholder_description("   ") is True

    def test_dispatcher_template_is_placeholder(self):
        from ai_ops.agents.builder import BuilderAgent
        assert BuilderAgent._is_placeholder_description("Builder phase for: ...") is True
        assert BuilderAgent._is_placeholder_description("builder phase for: ...") is True
        assert BuilderAgent._is_placeholder_description("Builder phase for: ") is True
        assert BuilderAgent._is_placeholder_description("Builder phase for:") is True

    def test_ellipsis_remainder_is_placeholder(self):
        from ai_ops.agents.builder import BuilderAgent
        assert BuilderAgent._is_placeholder_description("Builder phase for: \u2026") is True

    def test_valid_description_is_not_placeholder(self):
        from ai_ops.agents.builder import BuilderAgent
        assert BuilderAgent._is_placeholder_description("Implement add(a, b)") is False
        assert BuilderAgent._is_placeholder_description("Build a REST API for user auth") is False
        assert BuilderAgent._is_placeholder_description("Builder phase for: authentication module") is False

    # ------------------------------------------------------------------
    # Behavior tests
    # ------------------------------------------------------------------

    def test_placeholder_description_produces_escalated_status(self):
        """Builder.run() returns ESCALATED when description is a placeholder."""
        from ai_ops.agents.base import TaskStatus
        output = self._run_builder("Builder phase for: ...")
        assert output.status == TaskStatus.ESCALATED, (
            f"Expected ESCALATED, got {output.status}"
        )

    def test_placeholder_description_writes_no_files(self, tmp_path):
        """No files are written to worktree when description is a placeholder."""
        from ai_ops.tools.file_tools import FileTools

        worktree = tmp_path / "wt"
        worktree.mkdir()

        write_calls = []
        original = FileTools.write_file

        def tracking_write(self_ft, path, content):
            write_calls.append(path)
            return original(self_ft, path, content)

        import unittest.mock as mock
        with mock.patch.object(FileTools, "write_file", tracking_write):
            self._run_builder("Builder phase for: ...", worktree_path=str(worktree))

        assert write_calls == [], (
            f"write_file was called with {write_calls} on a placeholder task"
        )

    def test_placeholder_description_has_escalation_in_output(self):
        """Result contains escalation_reason and empty files_written."""
        output = self._run_builder("Builder phase for: ...")
        assert "escalation_reason" in output.result
        assert output.result.get("files_written") == []
        assert len(output.escalations) > 0

    def test_tool_loop_does_not_fire_on_placeholder(self, tmp_path):
        """complete_with_tools is never called when description is a placeholder."""
        from ai_ops.agents.base import AgentInput
        from ai_ops.agents.builder import BuilderAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        tool_loop_called = []

        class _TrackingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=10):
                tool_loop_called.append(True)
                return "{}", []

            def complete(self_inner, system, user, expect_json=False):
                return "{}"

        agent = BuilderAgent(llm_client=_TrackingClient())
        agent_input = AgentInput(
            run_id="esc-llm",
            description="Builder phase for: ...",
            acceptance_criteria=[],
            context={"worktree_path": str(worktree)},
        )
        agent.run(agent_input)

        assert tool_loop_called == [], "complete_with_tools was called on a placeholder task"

    def test_valid_description_proceeds_normally(self):
        """Valid description bypasses escalation and reaches normal execution."""
        from ai_ops.agents.base import TaskStatus
        output = self._run_builder("Implement add(a, b) that returns the sum")
        assert output.status == TaskStatus.COMPLETED, (
            f"Valid task should complete, got {output.status}"
        )


# ===========================================================================
# TestReviewerToolLoop
# ===========================================================================


class TestReviewerToolLoop:
    """Tests for ReviewerAgent tool-call loop (LLM mode with worktree)."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    _VERDICT_JSON = (
        '{"verdict": "PASS", "verdict_reason": "all checks passed",'
        ' "acceptance_criteria": [], "automated_checks": [], "findings": [],'
        ' "policy_compliance": [], "plan_adherence": {"matches_plan": "YES", "deviations": "none"},'
        ' "missing_items": [], "summary": "ok", "recommendation": "approve"}'
    )

    @staticmethod
    def _make_tool_client(calls_to_make: list[tuple[str, dict]], final_json: str):
        """Fake LLM client that drives tool_executor with calls_to_make, then returns final_json."""

        class _FakeToolClient:
            provider_name = "fake"
            model_name = "fake-reviewer-v1"

            def complete_with_tools(
                self_inner, system, user, tools, tool_executor, max_iterations=8
            ):
                log = []
                for name, inputs in calls_to_make:
                    result = tool_executor(name, inputs)
                    log.append({"tool": name, "input": inputs, "result": result})
                return final_json, log

            def complete(self_inner, system, user, expect_json=False):
                return final_json

        return _FakeToolClient()

    @staticmethod
    def _make_agent_input(
        worktree_path: str = "",
        files_written: list[str] | None = None,
    ) -> "AgentInput":
        from ai_ops.agents.base import AgentInput

        return AgentInput(
            run_id="rev-loop-test",
            description="Review the build",
            acceptance_criteria=["add works"],
            context={
                "worktree_path": worktree_path,
                "build_output": {"files_written": files_written or []},
            },
        )

    # ------------------------------------------------------------------
    # Routing tests
    # ------------------------------------------------------------------

    def test_routes_to_tool_loop_when_worktree_and_tool_client(self, tmp_path):
        """_execute_llm calls complete_with_tools when worktree+tool client present."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        calls_log = []

        class _TrackingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=8):
                calls_log.append("complete_with_tools")
                return self._VERDICT_JSON, []

            def complete(self_inner, system, user, expect_json=False):
                calls_log.append("complete")
                return self._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_TrackingClient())
        agent._execute_llm(
            self._make_agent_input(worktree_path=str(worktree)),
            AgentOutput(task_id="t1", agent_role="reviewer"),
        )

        assert "complete_with_tools" in calls_log
        assert "complete" not in calls_log

    def test_falls_back_to_oneshot_without_worktree(self):
        """Without worktree_path, _execute_llm uses complete() not complete_with_tools."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        calls_log = []

        class _TrackingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=8):
                calls_log.append("complete_with_tools")
                return self._VERDICT_JSON, []

            def complete(self_inner, system, user, expect_json=False):
                calls_log.append("complete")
                return self._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_TrackingClient())
        agent._execute_llm(
            self._make_agent_input(worktree_path=""),
            AgentOutput(task_id="t2", agent_role="reviewer"),
        )

        assert "complete" in calls_log
        assert "complete_with_tools" not in calls_log

    def test_falls_back_to_oneshot_when_client_lacks_tool_support(self, tmp_path):
        """When client has no complete_with_tools, falls back to complete()."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()
        calls_log = []

        class _NoToolClient:
            provider_name = "fake"
            model_name = "fake"

            def complete(self_inner, system, user, expect_json=False):
                calls_log.append("complete")
                return self._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_NoToolClient())
        agent._execute_llm(
            self._make_agent_input(worktree_path=str(worktree)),
            AgentOutput(task_id="t3", agent_role="reviewer"),
        )

        assert "complete" in calls_log

    # ------------------------------------------------------------------
    # Tool executor behaviour
    # ------------------------------------------------------------------

    def test_run_ruff_uses_files_written_scope_by_default(self, tmp_path, monkeypatch):
        """run_ruff tool call with no paths defaults to files_written list."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "add.py").write_text("def add(a, b): return a + b\n")

        ruff_paths_seen = []
        monkeypatch.setattr(
            ShellTools, "run_ruff",
            lambda self, paths=None: (ruff_paths_seen.append(paths) or ShellResult(0, "ok", "")),
        )

        agent = ReviewerAgent(
            llm_client=self._make_tool_client(
                [("run_ruff", {})],  # no paths — should default
                self._VERDICT_JSON,
            )
        )
        agent._execute_llm(
            self._make_agent_input(
                worktree_path=str(worktree),
                files_written=["add.py"],
            ),
            AgentOutput(task_id="t4", agent_role="reviewer"),
        )

        assert ruff_paths_seen, "run_ruff was not called"
        assert ruff_paths_seen[0] == ["add.py"], (
            f"Expected ['add.py'], got {ruff_paths_seen[0]}"
        )

    def test_run_mypy_filters_to_py_files(self, tmp_path, monkeypatch):
        """run_mypy tool call filters paths to .py files only."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()

        mypy_paths_seen = []
        monkeypatch.setattr(
            ShellTools, "run_mypy",
            lambda self, paths=None: (mypy_paths_seen.append(paths) or ShellResult(0, "ok", "")),
        )

        agent = ReviewerAgent(
            llm_client=self._make_tool_client(
                [("run_mypy", {})],
                self._VERDICT_JSON,
            )
        )
        agent._execute_llm(
            self._make_agent_input(
                worktree_path=str(worktree),
                files_written=["add.py", "README.md", "tests/test_add.py"],
            ),
            AgentOutput(task_id="t5", agent_role="reviewer"),
        )

        assert mypy_paths_seen, "run_mypy was not called"
        assert "README.md" not in mypy_paths_seen[0], "non-.py file passed to mypy"
        assert "add.py" in mypy_paths_seen[0]

    def test_run_pytest_scoped_to_test_files_by_default(self, tmp_path, monkeypatch):
        """run_pytest tool call with no paths uses only test_*.py files from files_written."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.tools.shell_tools import ShellTools, ShellResult

        worktree = tmp_path / "wt"
        worktree.mkdir()

        pytest_paths_seen = []
        monkeypatch.setattr(
            ShellTools, "run_pytest",
            lambda self, paths=None: (pytest_paths_seen.append(paths) or ShellResult(0, "1 passed", "")),
        )

        agent = ReviewerAgent(
            llm_client=self._make_tool_client(
                [("run_pytest", {})],
                self._VERDICT_JSON,
            )
        )
        agent._execute_llm(
            self._make_agent_input(
                worktree_path=str(worktree),
                files_written=["add.py", "tests/test_add.py"],
            ),
            AgentOutput(task_id="t6", agent_role="reviewer"),
        )

        assert pytest_paths_seen, "run_pytest was not called"
        assert pytest_paths_seen[0] == ["tests/test_add.py"], (
            f"Expected ['tests/test_add.py'], got {pytest_paths_seen[0]}"
        )

    def test_read_file_returns_worktree_content(self, tmp_path):
        """read_file tool call returns file contents from the worktree."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / "add.py").write_text("def add(a, b): return a + b\n")

        tool_results = []

        class _RecordingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(
                self_inner, system, user, tools, tool_executor, max_iterations=8
            ):
                result = tool_executor("read_file", {"path": "add.py"})
                tool_results.append(result)
                return self._VERDICT_JSON, [{"tool": "read_file", "result": result}]

            def complete(self_inner, *a, **kw):
                return self._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_RecordingClient())
        agent._execute_llm(
            self._make_agent_input(
                worktree_path=str(worktree),
                files_written=["add.py"],
            ),
            AgentOutput(task_id="t7", agent_role="reviewer"),
        )

        assert tool_results, "read_file was not called"
        assert "def add" in tool_results[0]

    def test_tool_call_count_in_output(self, tmp_path):
        """tool_call_count is present in output.result when tool loop runs."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        agent = ReviewerAgent(
            llm_client=self._make_tool_client(
                [("run_ruff", {}), ("run_pytest", {})],
                self._VERDICT_JSON,
            )
        )
        output = agent._execute_llm(
            self._make_agent_input(worktree_path=str(worktree), files_written=[]),
            AgentOutput(task_id="t8", agent_role="reviewer"),
        )

        assert "tool_call_count" in output.result

    # ------------------------------------------------------------------
    # Pre-injection behavior (API call reduction)
    # ------------------------------------------------------------------

    def test_pre_run_checks_injected_when_files_written(self, tmp_path, monkeypatch):
        """automated_checks_results is injected into context before the tool loop
        when files_written is non-empty, reducing API roundtrips."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        fake_check_results = {
            "ruff": {"status": "PASS", "returncode": 0, "output": ""},
            "mypy": {"status": "PASS", "returncode": 0, "output": ""},
        }
        monkeypatch.setattr(
            ReviewerAgent,
            "_run_automated_checks",
            lambda self, path, files_written=None: fake_check_results,
        )

        user_seen = []

        class _RecordingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=8):
                user_seen.append(user)
                return TestReviewerToolLoop._VERDICT_JSON, []

            def complete(self_inner, *a, **kw):
                return TestReviewerToolLoop._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_RecordingClient())
        agent._execute_llm(
            self._make_agent_input(worktree_path=str(worktree), files_written=["foo.py"]),
            AgentOutput(task_id="t9", agent_role="reviewer"),
        )

        assert user_seen, "complete_with_tools was not called"
        # automated_checks_results must appear in the user message sent to the model
        assert "automated_checks_results" in user_seen[0], (
            "automated_checks_results not found in user message — pre-injection failed"
        )

    def test_loop_tools_restricted_to_read_file_when_pre_run_succeeds(self, tmp_path, monkeypatch):
        """When pre-run checks return results, only read_file is offered to the model."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent

        worktree = tmp_path / "wt"
        worktree.mkdir()

        monkeypatch.setattr(
            ReviewerAgent,
            "_run_automated_checks",
            lambda self, path, files_written=None: {
                "ruff": {"status": "PASS", "returncode": 0, "output": ""},
            },
        )

        tools_seen = []

        class _RecordingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=8):
                tools_seen.append(tools)
                return TestReviewerToolLoop._VERDICT_JSON, []

            def complete(self_inner, *a, **kw):
                return TestReviewerToolLoop._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_RecordingClient())
        agent._execute_llm(
            self._make_agent_input(worktree_path=str(worktree), files_written=["foo.py"]),
            AgentOutput(task_id="t10", agent_role="reviewer"),
        )

        assert tools_seen, "complete_with_tools was not called"
        tool_names = [t["name"] for t in tools_seen[0]]
        assert tool_names == ["read_file"], (
            f"Expected only ['read_file'] in loop_tools, got {tool_names}"
        )

    def test_loop_tools_include_all_when_files_written_empty(self, tmp_path):
        """When files_written is empty, the full _REVIEWER_TOOLS set is passed to the loop."""
        from ai_ops.agents.base import AgentOutput
        from ai_ops.agents.reviewer import ReviewerAgent
        from ai_ops.agents.reviewer import _REVIEWER_TOOLS

        worktree = tmp_path / "wt"
        worktree.mkdir()

        tools_seen = []

        class _RecordingClient:
            provider_name = "fake"
            model_name = "fake"

            def complete_with_tools(self_inner, system, user, tools, tool_executor, max_iterations=8):
                tools_seen.append(tools)
                return TestReviewerToolLoop._VERDICT_JSON, []

            def complete(self_inner, *a, **kw):
                return TestReviewerToolLoop._VERDICT_JSON

        agent = ReviewerAgent(llm_client=_RecordingClient())
        agent._execute_llm(
            self._make_agent_input(worktree_path=str(worktree), files_written=[]),
            AgentOutput(task_id="t11", agent_role="reviewer"),
        )

        assert tools_seen, "complete_with_tools was not called"
        assert tools_seen[0] == _REVIEWER_TOOLS, (
            f"Expected full _REVIEWER_TOOLS, got {[t['name'] for t in tools_seen[0]]}"
        )


# ---------------------------------------------------------------------------
# Dispatcher subtask quality hardening
# ---------------------------------------------------------------------------

class TestDispatcherSubtaskQuality:
    """Tests for template-description detection and sanitization gate."""

    def setup_method(self):
        from workflows.langgraph.graphs.dispatch_pipeline import (
            _is_template_subtask_description,
            _sanitize_plan_subtask_descriptions,
        )
        self._is_template = _is_template_subtask_description
        self._sanitize = _sanitize_plan_subtask_descriptions

    # ------------------------------------------------------------------
    # _is_template_subtask_description
    # ------------------------------------------------------------------

    def test_template_description_detected(self):
        """Known template patterns must be detected as templates."""
        assert self._is_template("Builder phase for: ...")
        assert self._is_template("Research phase for: some task")
        assert self._is_template("reviewer phase for:")
        assert self._is_template("BUILDER PHASE FOR: anything")
        assert self._is_template("")
        assert self._is_template("   ")

    def test_concrete_description_not_detected(self):
        """Concrete descriptions must not be flagged as templates."""
        assert not self._is_template("Implement add(a, b)")
        assert not self._is_template("Review the implementation for correctness")
        assert not self._is_template("Research optimal data structures for this task")
        assert not self._is_template("Build a user authentication module")

    # ------------------------------------------------------------------
    # _sanitize_plan_subtask_descriptions
    # ------------------------------------------------------------------

    def test_sanitize_replaces_template_descriptions(self):
        """Template subtask descriptions are replaced with task_description."""
        plan = {
            "run_id": "test-001",
            "subtasks": [
                {"id": 1, "assigned_agent": "research", "description": "Research phase for: ...", "depends_on": []},
                {"id": 2, "assigned_agent": "builder", "description": "Builder phase for: ...", "depends_on": [1]},
            ],
            "execution_order": [1, 2],
        }
        task_desc = "Implement add(a, b)"
        result = self._sanitize(plan, task_desc)

        assert result is not plan  # new dict returned when replacements made
        for subtask in result["subtasks"]:
            assert subtask["description"] == task_desc
        # Other fields preserved
        assert result["run_id"] == "test-001"
        assert result["execution_order"] == [1, 2]

    def test_sanitize_leaves_concrete_descriptions_alone(self):
        """Concrete descriptions are left untouched; original plan object returned."""
        plan = {
            "run_id": "test-002",
            "subtasks": [
                {"id": 1, "assigned_agent": "research", "description": "Research optimal sort algorithms", "depends_on": []},
                {"id": 2, "assigned_agent": "builder", "description": "Implement the sort module", "depends_on": [1]},
            ],
            "execution_order": [1, 2],
        }
        result = self._sanitize(plan, "some task")
        assert result is plan  # same object — no copy when no replacements

    def test_sanitize_handles_empty_or_malformed_plan(self):
        """Edge cases must not raise."""
        # Empty plan
        assert self._sanitize({}, "task") == {}
        # Missing task_description
        plan = {"subtasks": [{"id": 1, "description": "Builder phase for: ..."}]}
        assert self._sanitize(plan, "") is plan
        assert self._sanitize(plan, None) is plan  # type: ignore[arg-type]
        # Non-list subtasks
        plan2 = {"subtasks": "not a list"}
        assert self._sanitize(plan2, "task") is plan2

    # ------------------------------------------------------------------
    # Integration: pipeline produces concrete subtask descriptions
    # ------------------------------------------------------------------

    def test_pipeline_builder_receives_concrete_description(self, stub_pipeline):
        """No subtask in a completed pipeline has a template description."""
        import re
        template_re = re.compile(r"^\w+\s+phase\s+for\s*:", re.IGNORECASE)

        pipeline, _repo_root = stub_pipeline
        result = pipeline.invoke({
            "run_id": "quality-gate-test-001",
            "task_description": "Implement a function that adds two numbers",
            "acceptance_criteria": ["add(1, 2) returns 3"],
            "constraints": [],
            "approval_level": 0,
        })

        dispatcher_output = result.get("dispatcher_output", {})
        plan = dispatcher_output.get("plan", {})
        subtasks = plan.get("subtasks", [])

        assert subtasks, "Expected at least one subtask in dispatcher plan"
        for subtask in subtasks:
            desc = subtask.get("description", "")
            assert not template_re.match(desc), (
                f"Subtask {subtask.get('id')} has a template description: {desc!r}"
            )
