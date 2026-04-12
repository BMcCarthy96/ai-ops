"""
LangGraph Task Schema — Pydantic models for task validation.

These schemas validate the inputs and outputs of the orchestration pipeline.
They complement the RunState TypedDict used by LangGraph.

Phase 1: Functional validation schemas. Used by the graph nodes to validate
         inputs before passing to agents.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Types of tasks the system can handle."""

    RESEARCH = "research"
    BUILD = "build"
    FIX = "fix"
    REVIEW = "review"
    INVESTIGATE = "investigate"
    MULTI_STAGE = "multi-stage"


class Complexity(str, Enum):
    """Task complexity levels."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class Urgency(str, Enum):
    """Task urgency levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskBrief(BaseModel):
    """
    Schema for a task submitted to the pipeline.
    Corresponds to the templates/task-brief.md structure.
    """

    title: str
    description: str
    requester: str = "operator"
    priority: Urgency = Urgency.NORMAL
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    scope_in: list[str] = Field(default_factory=list)
    scope_out: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class TaskClassification(BaseModel):
    """Schema for the Dispatcher's task classification output."""

    task_type: TaskType
    complexity: Complexity
    estimated_subtasks: int
    required_agents: list[str]
    required_skills: list[str] = Field(default_factory=list)
    approval_level: int = 0
    urgency: Urgency = Urgency.NORMAL
    risks: list[str] = Field(default_factory=list)


class SubtaskAssignment(BaseModel):
    """Schema for a subtask assigned to a specialist agent."""

    id: int
    description: str
    assigned_agent: str
    skills: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)
    approval_level: int = 0


class ExecutionPlan(BaseModel):
    """Schema for the Dispatcher's execution plan."""

    run_id: str
    subtasks: list[SubtaskAssignment]
    execution_order: list[int]
    estimated_total_time: str = "unknown"


class ResearchOutput(BaseModel):
    """Schema for the Research agent's output."""

    research_question: str
    findings: list = Field(default_factory=list)
    assumptions: list = Field(default_factory=list)
    recommendations: dict = Field(default_factory=dict)
    gaps: list = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)


class BuilderOutput(BaseModel):
    """Schema for the Builder agent's output."""

    implementation_summary: str
    research_context_received: bool = False
    files_changed: dict = Field(default_factory=dict)
    tests_created: list = Field(default_factory=list)
    dependencies_added: list = Field(default_factory=list)
    deviations_from_plan: str = "none"


class ReviewVerdict(str, Enum):
    """Possible review outcomes."""

    PASS = "PASS"
    PASS_WITH_ISSUES = "PASS WITH ISSUES"
    FAIL = "FAIL"


class ReviewResult(BaseModel):
    """Schema for the Reviewer agent's output."""

    verdict: ReviewVerdict
    verdict_reason: str = ""
    build_context_received: bool = False
    acceptance_criteria: list[dict] = Field(default_factory=list)
    automated_checks: list = Field(default_factory=list)   # list of {check, tool, status, details}
    findings: list = Field(default_factory=list)
    policy_compliance: list = Field(default_factory=list)  # list of {policy, status, notes}
    plan_adherence: dict = Field(default_factory=dict)     # {matches_plan: str, deviations: str}
    missing_items: list = Field(default_factory=list)
    recommendation: str = ""
