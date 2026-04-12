"""
Tests for AI Ops agent classes.

Tests all four agents in stub mode (no API key needed).
Verifies the base interface, approval gating, classification,
plan generation, and structured output formats.
"""

from ai_ops.agents.base import (
    AgentInput,
    AgentOutput,
    ApprovalLevel,
    TaskStatus,
)
from ai_ops.agents.builder import BuilderAgent
from ai_ops.agents.dispatcher import DispatcherAgent
from ai_ops.agents.research import ResearchAgent
from ai_ops.agents.reviewer import ReviewerAgent
from ai_ops.llm.client import StubClient


class TestBaseAgentInterface:
    """Test the base agent interface contract."""

    def test_agent_input_defaults(self):
        """AgentInput should have sensible defaults."""
        inp = AgentInput()
        assert inp.task_id != ""
        assert inp.approval_level == ApprovalLevel.AUTO
        assert inp.constraints == []
        assert inp.acceptance_criteria == []

    def test_agent_output_defaults(self):
        """AgentOutput should have sensible defaults."""
        out = AgentOutput()
        assert out.status == TaskStatus.PENDING
        assert out.issues == []
        assert out.escalations == []

    def test_approval_gating(self):
        """Agents should pause on Level 2+ approval requirements."""
        agent = ResearchAgent(llm_client=StubClient())
        inp = AgentInput(
            description="Test task",
            approval_level=ApprovalLevel.HARD,
        )
        result = agent.run(inp)
        assert result.status == TaskStatus.WAITING_APPROVAL

    def test_approval_level_3_blocked(self):
        """Level 3 should also trigger waiting_approval in the agent."""
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(
            description="Delete production data",
            approval_level=ApprovalLevel.BLOCKED,
        )
        result = agent.run(inp)
        assert result.status == TaskStatus.WAITING_APPROVAL

    def test_stub_mode_detection(self):
        """Agents should correctly detect stub mode."""
        agent = ResearchAgent(llm_client=StubClient())
        assert agent.is_stub_mode is True

    def test_agent_repr(self):
        """Agent repr should include role and provider."""
        agent = DispatcherAgent(llm_client=StubClient())
        r = repr(agent)
        assert "dispatcher" in r
        assert "stub" in r


class TestDispatcherAgent:
    """Test the Dispatcher agent."""

    def test_instantiation(self):
        agent = DispatcherAgent(llm_client=StubClient())
        assert agent.name == "dispatcher"

    def test_run_returns_output(self):
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(
            run_id="test-001",
            description="Build a login page",
            acceptance_criteria=["Login form", "Validation"],
        )
        result = agent.run(inp)
        assert result.status == TaskStatus.COMPLETED
        assert "classification" in result.result
        assert "plan" in result.result

    def test_classification_research(self):
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(description="Research Python web frameworks")
        result = agent.run(inp)
        classification = result.result["classification"]
        assert classification["task_type"] == "research"
        assert "research" in classification["required_agents"]

    def test_classification_build(self):
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(description="Build a REST API service")
        result = agent.run(inp)
        classification = result.result["classification"]
        assert classification["task_type"] == "build"
        assert "builder" in classification["required_agents"]

    def test_classification_fix(self):
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(description="Fix the login bug in auth module")
        result = agent.run(inp)
        classification = result.result["classification"]
        assert classification["task_type"] == "fix"

    def test_plan_has_subtasks(self):
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(
            run_id="test-002",
            description="Build authentication module",
        )
        result = agent.run(inp)
        plan = result.result["plan"]
        assert "subtasks" in plan
        assert len(plan["subtasks"]) > 0
        assert "execution_order" in plan

    def test_stub_mode_notes(self):
        """Stub mode should indicate it in the notes."""
        agent = DispatcherAgent(llm_client=StubClient())
        inp = AgentInput(description="Do something")
        result = agent.run(inp)
        assert "stub" in result.notes.lower()


class TestResearchAgent:
    """Test the Research agent."""

    def test_instantiation(self):
        agent = ResearchAgent(llm_client=StubClient())
        assert agent.name == "research"

    def test_run_returns_structured_output(self):
        agent = ResearchAgent(llm_client=StubClient())
        inp = AgentInput(
            run_id="test-003",
            description="Compare JWT libraries for Python",
        )
        result = agent.run(inp)
        assert result.status == TaskStatus.COMPLETED
        assert "findings" in result.result
        assert "assumptions" in result.result
        assert "recommendations" in result.result

    def test_skill_prefix(self):
        agent = ResearchAgent(llm_client=StubClient())
        assert agent.can_handle("research.compare.tools")
        assert not agent.can_handle("coding.scaffold.service")


class TestBuilderAgent:
    """Test the Builder agent."""

    def test_instantiation(self):
        agent = BuilderAgent(llm_client=StubClient())
        assert agent.name == "builder"

    def test_run_returns_structured_output(self):
        agent = BuilderAgent(llm_client=StubClient())
        inp = AgentInput(
            run_id="test-004",
            description="Scaffold auth module",
            context={"research_output": {"findings": []}},
        )
        result = agent.run(inp)
        assert result.status == TaskStatus.COMPLETED
        assert "files_changed" in result.result
        assert "branch" in result.result
        assert result.result["research_context_received"] is True

    def test_skill_prefix(self):
        agent = BuilderAgent(llm_client=StubClient())
        assert agent.can_handle("coding.scaffold.service")
        assert not agent.can_handle("research.compare.tools")


class TestReviewerAgent:
    """Test the Reviewer agent."""

    def test_instantiation(self):
        agent = ReviewerAgent(llm_client=StubClient())
        assert agent.name == "reviewer"

    def test_run_returns_structured_output(self):
        agent = ReviewerAgent(llm_client=StubClient())
        inp = AgentInput(
            run_id="test-005",
            description="Review auth module implementation",
            acceptance_criteria=["JWT support", "Password hashing"],
            context={"build_output": {"files_changed": {}}},
        )
        result = agent.run(inp)
        assert result.status == TaskStatus.COMPLETED
        assert "verdict" in result.result
        assert "acceptance_criteria" in result.result
        assert result.result["build_context_received"] is True

    def test_stub_verdict_is_pass(self):
        """Stub mode reviewer should return PASS."""
        agent = ReviewerAgent(llm_client=StubClient())
        inp = AgentInput(description="Review something")
        result = agent.run(inp)
        assert result.result["verdict"] == "PASS"

    def test_acceptance_criteria_checking(self):
        agent = ReviewerAgent(llm_client=StubClient())
        criteria = ["Criterion A", "Criterion B", "Criterion C"]
        inp = AgentInput(
            description="Review something",
            acceptance_criteria=criteria,
        )
        result = agent.run(inp)
        checked = result.result["acceptance_criteria"]
        assert len(checked) == len(criteria)
        for item in checked:
            assert "criterion" in item
            assert "status" in item

    def test_skill_prefix(self):
        agent = ReviewerAgent(llm_client=StubClient())
        assert agent.can_handle("qa.review.implementation")
        assert not agent.can_handle("coding.fix.bug")
