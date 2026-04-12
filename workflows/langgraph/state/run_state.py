"""
LangGraph Run State — State object for the dispatch pipeline.

Defines the shared state that flows between nodes in the LangGraph
orchestration graph. Each node (agent) reads from and writes to this state.
"""

from __future__ import annotations

from typing import Any, TypedDict


class RunState(TypedDict, total=False):
    """
    Shared state for the Dispatcher → Research → Builder → Reviewer pipeline.

    This state is passed between nodes in the LangGraph graph. Each node
    reads the fields it needs and writes its output to the appropriate field.
    """

    # Input fields — set at pipeline start
    run_id: str
    task_description: str
    acceptance_criteria: list[str]
    constraints: list[str]
    approval_level: int

    # Agent output fields — populated as agents execute
    dispatcher_output: dict[str, Any]
    research_output: dict[str, Any]
    builder_output: dict[str, Any]
    reviewer_output: dict[str, Any]

    # Pipeline control fields
    current_stage: str
    status: str
    errors: list[str]
    escalations: list[str]

    # Approval tracking
    approval_decisions: list[dict[str, Any]]

    # Persistence
    run_dir: str
    started_at: str
