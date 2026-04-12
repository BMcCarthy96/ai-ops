"""
LangGraph Dispatch Pipeline — Orchestration graph for AI Ops.

Defines the Dispatcher → Research → Builder → Reviewer pipeline
using LangGraph. Supports real LLM calls (Anthropic) or stub mode.

Usage:
    from workflows.langgraph.graphs.dispatch_pipeline import create_pipeline

    pipeline = create_pipeline()  # uses StubClient if no API key
    result = pipeline.invoke({
        "run_id": "2026-04-12-test-run",
        "task_description": "Build a user authentication module",
        "acceptance_criteria": ["JWT support", "Password hashing"],
        "constraints": ["Use Python 3.11+"],
        "approval_level": 0,
    })
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add the src directory to the path
_src_path = str(Path(__file__).resolve().parents[3] / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from ai_ops.agents.base import AgentInput, ApprovalLevel, TaskStatus
from ai_ops.agents.builder import BuilderAgent
from ai_ops.agents.dispatcher import DispatcherAgent
from ai_ops.agents.research import ResearchAgent
from ai_ops.agents.reviewer import ReviewerAgent
from ai_ops.llm.client import LLMClient, StubClient, create_client
from ai_ops.runtime.approval import ApprovalHandler, ApprovalResult, AutoApprovalHandler
from ai_ops.runtime.persistence import RunPersistence

from langgraph.graph import END, StateGraph

from pydantic import ValidationError

from workflows.langgraph.schemas.task_schema import (
    BuilderOutput,
    ExecutionPlan,
    ResearchOutput,
    ReviewResult,
    TaskClassification,
)
from workflows.langgraph.state.run_state import RunState


# ─────────────────────────────────────────────────────────
# Known agent names — used by the routing guard in dispatcher_node.
# Extend this set when new executable agents are added to the pipeline.
# ─────────────────────────────────────────────────────────

_KNOWN_AGENTS: frozenset[str] = frozenset({"research", "builder", "reviewer"})

# Alias map: lowercase LLM-produced names → canonical pipeline names.
# Handles title-case and role-style variants that real LLMs commonly emit.
# Add entries here when new patterns are observed in live runs.
_AGENT_NAME_ALIASES: dict[str, str] = {
    "research": "research",
    "researcher": "research",
    "builder": "builder",
    "engineer": "builder",
    "developer": "builder",
    "dev": "builder",
    "reviewer": "reviewer",
    "review": "reviewer",
    "qa": "reviewer",
    "tester": "reviewer",
}


# ─────────────────────────────────────────────────────────
# Pipeline configuration — set by create_pipeline()
# Using module-level vars so node functions can access them.
# This is intentional: LangGraph nodes are plain functions.
# ─────────────────────────────────────────────────────────

_llm_client: LLMClient = StubClient()
_approval_handler: ApprovalHandler = AutoApprovalHandler()
_persistence: RunPersistence = RunPersistence()
_persist_results: bool = True


# ─────────────────────────────────────────────────────────
# Node Functions
# ─────────────────────────────────────────────────────────


def init_node(state: RunState) -> dict[str, Any]:
    """Initialize the run: create run directory, record start time."""
    run_id = state.get("run_id", "")
    started_at = datetime.now(timezone.utc).isoformat()
    run_dir = ""

    if _persist_results and run_id:
        path = _persistence.create_run_dir(run_id)
        run_dir = str(path)

    return {
        "started_at": started_at,
        "run_dir": run_dir,
        "current_stage": "initialized",
        "status": "running",
        "errors": [],
        "escalations": [],
        "approval_decisions": [],
    }


def dispatcher_node(state: RunState) -> dict[str, Any]:
    """Dispatcher node — classifies the task and creates an execution plan."""
    agent = DispatcherAgent(llm_client=_llm_client)
    agent_input = AgentInput(
        run_id=state.get("run_id", ""),
        description=state.get("task_description", ""),
        acceptance_criteria=state.get("acceptance_criteria", []),
        constraints=state.get("constraints", []),
        approval_level=ApprovalLevel(state.get("approval_level", 0)),
    )

    output = agent.run(agent_input)

    # Normalize required_agents before validation and routing.
    # Real LLMs often return title-case or role-style names (e.g. "Researcher",
    # "Engineer"). Normalise in-place so the router and validation both see
    # canonical lowercase names. Unknown names are lowercased but kept as-is;
    # the routing guard below will catch them.
    if output.status == TaskStatus.COMPLETED:
        _cls = output.result.get("classification")
        if isinstance(_cls, dict) and isinstance(_cls.get("required_agents"), list):
            _raw: list[str] = _cls["required_agents"]
            _normalized = [
                _AGENT_NAME_ALIASES.get(n.lower(), n.lower())
                for n in _raw
                if isinstance(n, str)
            ]
            if _normalized != _raw:
                logging.info(
                    "dispatcher required_agents normalized: %r → %r",
                    _raw,
                    _normalized,
                )
                _cls["required_agents"] = _normalized

    # Schema validation and routing guards only apply when the dispatcher completed
    # normally. If the base agent returned early (WAITING_APPROVAL when
    # approval_level >= HARD, or FAILED on crash), output.result is empty —
    # validating it would produce misleading schema errors for what is actually
    # an approval or runtime issue, not a classification problem.
    _schema_errors: list[str] = []
    if output.status == TaskStatus.COMPLETED:
        try:
            TaskClassification.model_validate(output.result.get("classification", {}))
        except ValidationError as _exc:
            _msg = f"dispatcher classification schema invalid: {_exc.error_count()} error(s)"
            logging.warning(_msg)
            _schema_errors.append(_msg)
        try:
            ExecutionPlan.model_validate(output.result.get("plan", {}))
        except ValidationError as _exc:
            _msg = f"dispatcher plan schema invalid: {_exc.error_count()} error(s)"
            logging.warning(_msg)
            _schema_errors.append(_msg)

        # Routing guard: warn if required_agents is missing or empty.
        # route_after_approval cannot modify state, so this is the only place to
        # make the skip visible. An empty list causes all agent execution to be
        # silently skipped; the operator must see this in state["errors"].
        _classification = output.result.get("classification", {})
        _required_agents = (
            _classification.get("required_agents")
            if isinstance(_classification, dict)
            else None
        )
        if not _required_agents or not isinstance(_required_agents, list):
            _msg = (
                "dispatcher required_agents missing or empty — "
                "all agent execution will be skipped. "
                "Check dispatcher output or LLM classification response."
            )
            logging.warning(_msg)
            _schema_errors.append(_msg)
        elif not _KNOWN_AGENTS.intersection(_required_agents):
            _msg = (
                f"dispatcher required_agents contains no recognised agents "
                f"(got {_required_agents!r}, known: {sorted(_KNOWN_AGENTS)!r}) — "
                "all agent execution will be skipped."
            )
            logging.warning(_msg)
            _schema_errors.append(_msg)

    # Persist dispatcher output
    if _persist_results and state.get("run_id"):
        _persistence.save_agent_output(state["run_id"], "dispatcher", output.model_dump())

    return {
        "dispatcher_output": output.result,
        "current_stage": "dispatcher_complete",
        "status": output.status.value,
        "errors": state.get("errors", []) + output.issues + _schema_errors,
        "escalations": state.get("escalations", []) + output.escalations,
    }


def approval_gate_node(state: RunState) -> dict[str, Any]:
    """
    Check approval before proceeding to execution agents.

    Uses the approval_level from the initial state and the dispatcher's
    classification to determine if approval is needed.
    """
    level = state.get("approval_level", 0)
    task_desc = state.get("task_description", "unknown task")
    description = f"Execute pipeline for: {task_desc} (approval level {level})"

    result = _approval_handler.check(level, description)

    decision = {
        "stage": "pre_execution",
        "level": level,
        "result": result.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    decisions = list(state.get("approval_decisions", []))
    decisions.append(decision)

    if result == ApprovalResult.BLOCKED:
        return {
            "current_stage": "blocked",
            "status": "blocked",
            "approval_decisions": decisions,
            "errors": state.get("errors", []) + [f"Pipeline blocked: Level {level} action forbidden"],
        }
    elif result == ApprovalResult.DENIED:
        return {
            "current_stage": "denied",
            "status": "denied",
            "approval_decisions": decisions,
            "errors": state.get("errors", []) + [f"Pipeline denied: operator declined Level {level} approval"],
        }
    else:
        return {
            "current_stage": "approved",
            "status": "running",
            "approval_decisions": decisions,
        }


def research_node(state: RunState) -> dict[str, Any]:
    """Research node — investigates the topic and produces findings."""
    agent = ResearchAgent(llm_client=_llm_client)
    agent_input = AgentInput(
        run_id=state.get("run_id", ""),
        description=state.get("task_description", ""),
        constraints=state.get("constraints", []),
        context={"dispatcher_output": state.get("dispatcher_output", {})},
        assigned_by="dispatcher",
    )

    output = agent.run(agent_input)

    # Schema validation — non-blocking: log warning and accumulate errors, keep raw dict
    _schema_errors: list[str] = []
    try:
        ResearchOutput.model_validate(output.result)
    except ValidationError as _exc:
        _msg = f"research output schema invalid: {_exc.error_count()} error(s)"
        logging.warning(_msg)
        _schema_errors.append(_msg)

    if _persist_results and state.get("run_id"):
        _persistence.save_agent_output(state["run_id"], "research", output.model_dump())

    return {
        "research_output": output.result,
        "current_stage": "research_complete",
        "errors": state.get("errors", []) + output.issues + _schema_errors,
        "escalations": state.get("escalations", []) + output.escalations,
    }


def builder_node(state: RunState) -> dict[str, Any]:
    """Builder node — implements the plan based on research findings."""
    agent = BuilderAgent(llm_client=_llm_client)
    agent_input = AgentInput(
        run_id=state.get("run_id", ""),
        description=state.get("task_description", ""),
        acceptance_criteria=state.get("acceptance_criteria", []),
        context={"research_output": state.get("research_output", {})},
        assigned_by="dispatcher",
    )

    output = agent.run(agent_input)

    # Schema validation — non-blocking: log warning and accumulate errors, keep raw dict
    _schema_errors: list[str] = []
    try:
        BuilderOutput.model_validate(output.result)
    except ValidationError as _exc:
        _msg = f"builder output schema invalid: {_exc.error_count()} error(s)"
        logging.warning(_msg)
        _schema_errors.append(_msg)

    if _persist_results and state.get("run_id"):
        _persistence.save_agent_output(state["run_id"], "builder", output.model_dump())

    return {
        "builder_output": output.result,
        "current_stage": "builder_complete",
        "errors": state.get("errors", []) + output.issues + _schema_errors,
        "escalations": state.get("escalations", []) + output.escalations,
    }


def reviewer_node(state: RunState) -> dict[str, Any]:
    """Reviewer node — reviews the implementation or research against acceptance criteria."""
    agent = ReviewerAgent(llm_client=_llm_client)
    agent_input = AgentInput(
        run_id=state.get("run_id", ""),
        description=state.get("task_description", ""),
        acceptance_criteria=state.get("acceptance_criteria", []),
        context={
            "build_output": state.get("builder_output", {}),
            "research_output": state.get("research_output", {}),
            "task_type": (
                state.get("dispatcher_output", {})
                .get("classification", {})
                .get("task_type", "")
            ),
        },
        assigned_by="dispatcher",
    )

    output = agent.run(agent_input)

    # Schema validation — non-blocking: log warning and accumulate errors, keep raw dict
    _schema_errors: list[str] = []
    try:
        ReviewResult.model_validate(output.result)
    except ValidationError as _exc:
        _msg = f"reviewer output schema invalid: {_exc.error_count()} error(s)"
        logging.warning(_msg)
        _schema_errors.append(_msg)

    if _persist_results and state.get("run_id"):
        _persistence.save_agent_output(state["run_id"], "reviewer", output.model_dump())

    verdict = output.result.get("verdict", "FAIL")
    final_status = "completed" if verdict != "FAIL" else "needs_revision"

    return {
        "reviewer_output": output.result,
        "current_stage": "review_complete",
        "status": final_status,
        "errors": state.get("errors", []) + output.issues + _schema_errors,
        "escalations": state.get("escalations", []) + output.escalations,
    }


def persist_node(state: RunState) -> dict[str, Any]:
    """
    Final node: persist run summary, artifact index, and finalize run.
    """
    run_id = state.get("run_id", "")
    if not run_id or not _persist_results:
        return {"current_stage": "done"}

    # Build artifact index from all agent outputs
    artifacts = []
    for agent_name in ["dispatcher", "research", "builder", "reviewer"]:
        key = f"{agent_name}_output"
        if state.get(key):
            artifacts.append({
                "name": f"{agent_name}-output.yaml",
                "type": "agent_output",
                "agent": agent_name,
                "path": f"runs/completed/{run_id}/{agent_name}-output.yaml",
            })

    _persistence.save_artifact_index(run_id, artifacts)

    # Resolve terminal status BEFORE writing the summary so the summary file
    # always reflects the true final outcome. state["status"] may still be
    # "running" here when reviewer was not required (research-only/builder-only
    # runs) — resolving first ensures save_run_summary never writes "running".
    #
    # Finalize semantics:
    #   needs_revision  = pipeline ran fully, reviewer returned FAIL → completed/
    #   completed       = pipeline ran fully, reviewer passed        → completed/
    #   failed/blocked/denied/anything else                          → failed/
    status = state.get("status", "completed")

    if status == "running":
        any_agent_ran = any(
            state.get(f"{a}_output") is not None
            for a in ("research", "builder", "reviewer")
        )
        if any_agent_ran:
            # At least one agent executed — reviewer was simply not required.
            status = "completed"
        else:
            # No agent executed at all (routing guard fired, unknown agents, etc.).
            logging.warning(
                "persist_node: terminal status is still 'running' and no agent ran — "
                "resolving to 'failed'. Check state['errors'] for why execution was skipped."
            )
            status = "failed"

    # Save run summary with the resolved status, not the stale state value.
    _persistence.save_run_summary(run_id, {**state, "status": status})

    dir_status = "completed" if status in ("completed", "needs_revision") else "failed"
    _persistence.finalize_run(run_id, dir_status)

    # Always return status explicitly so result["status"] is the resolved terminal value.
    return {"current_stage": "done", "status": status}


# ─────────────────────────────────────────────────────────
# Routing Functions
# ─────────────────────────────────────────────────────────


def route_after_approval(state: RunState) -> str:
    """Route based on approval gate result."""
    status = state.get("status", "")
    if status in ("blocked", "denied"):
        return "persist"

    dispatcher_output = state.get("dispatcher_output", {})
    classification = dispatcher_output.get("classification", {})
    required_agents = classification.get("required_agents", [])

    if "research" in required_agents:
        return "research"
    elif "builder" in required_agents:
        return "builder"
    elif "reviewer" in required_agents:
        return "reviewer"
    else:
        logging.warning(
            "route_after_approval: no recognised agents in required_agents=%r — "
            "routing directly to persist. Check state['errors'] for details.",
            required_agents,
        )
        return "persist"


def _get_required_agents(state: RunState) -> list[str]:
    """Extract normalised required_agents from dispatcher classification."""
    dispatcher_output = state.get("dispatcher_output", {})
    classification = dispatcher_output.get("classification", {})
    return classification.get("required_agents", []) if isinstance(classification, dict) else []


def route_after_dispatcher(state: RunState) -> str:
    """Route after dispatcher: always go to approval gate."""
    if state.get("status") == "failed":
        return "persist"
    return "approval_gate"


def route_after_research(state: RunState) -> str:
    """After research: continue to builder only if dispatcher requested it."""
    required = _get_required_agents(state)
    if "builder" in required:
        return "builder"
    elif "reviewer" in required:
        return "reviewer"
    return "persist"


def route_after_builder(state: RunState) -> str:
    """After builder: continue to reviewer only if dispatcher requested it."""
    required = _get_required_agents(state)
    if "reviewer" in required:
        return "reviewer"
    return "persist"


def route_after_review(state: RunState) -> str:
    """After review, always go to persist."""
    return "persist"


# ─────────────────────────────────────────────────────────
# Graph Construction
# ─────────────────────────────────────────────────────────


def create_pipeline(
    llm_client: LLMClient | None = None,
    approval_handler: ApprovalHandler | None = None,
    persistence: RunPersistence | None = None,
    persist_results: bool = True,
) -> Any:
    """
    Create and compile the LangGraph dispatch pipeline.

    Args:
        llm_client: LLM client to use. Auto-detected if None.
        approval_handler: Approval handler. Defaults to AutoApprovalHandler.
        persistence: Persistence handler. Defaults to file-based.
        persist_results: Whether to persist results to disk.

    Returns:
        A compiled LangGraph that can be invoked.
    """
    # Set module-level config for node functions
    global _llm_client, _approval_handler, _persistence, _persist_results
    _llm_client = llm_client or create_client()
    _approval_handler = approval_handler or AutoApprovalHandler()
    _persistence = persistence or RunPersistence()
    _persist_results = persist_results

    # Build the graph
    graph = StateGraph(RunState)

    # Add nodes
    graph.add_node("init", init_node)
    graph.add_node("dispatcher", dispatcher_node)
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("research", research_node)
    graph.add_node("builder", builder_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("persist", persist_node)

    # Entry point
    graph.set_entry_point("init")

    # Edges
    graph.add_edge("init", "dispatcher")

    graph.add_conditional_edges(
        "dispatcher",
        route_after_dispatcher,
        {"approval_gate": "approval_gate", "persist": "persist"},
    )

    graph.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {
            "research": "research",
            "builder": "builder",
            "reviewer": "reviewer",
            "persist": "persist",
        },
    )

    graph.add_conditional_edges(
        "research",
        route_after_research,
        {"builder": "builder", "reviewer": "reviewer", "persist": "persist"},
    )
    graph.add_conditional_edges(
        "builder",
        route_after_builder,
        {"reviewer": "reviewer", "persist": "persist"},
    )

    graph.add_conditional_edges(
        "reviewer",
        route_after_review,
        {"persist": "persist"},
    )

    graph.add_edge("persist", END)

    return graph.compile()
