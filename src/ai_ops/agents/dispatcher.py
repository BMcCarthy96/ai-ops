"""
Dispatcher Agent — Central coordinator for AI Ops.

The Dispatcher receives tasks, classifies them, creates execution plans,
delegates to specialist agents, and consolidates results.

Uses LLM to classify tasks and generate intelligent execution plans.
Falls back to heuristic classification when in stub mode.
"""

from __future__ import annotations

import logging

from ai_ops.agents.base import (
    AgentInput,
    AgentOutput,
    AgentRole,
    BaseAgent,
    TaskStatus,
)
from ai_ops.llm.client import LLMClient

logger = logging.getLogger(__name__)


class DispatcherAgent(BaseAgent):
    """
    Central coordinator agent.

    Responsibilities:
    - Classify incoming tasks
    - Create execution plans with subtask assignments
    - Delegate to specialist agents
    - Consolidate results
    - Escalate when needed
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        super().__init__(AgentRole.DISPATCHER, llm_client)

    def execute(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """
        Process a task through classification, planning, and delegation.

        Calls the LLM for classification and planning, with heuristic fallback.
        """
        if self.is_stub_mode:
            return self._execute_stub(agent_input, output)

        return self._execute_llm(agent_input, output)

    def _execute_llm(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """LLM-powered classification and planning."""
        response = self.call_llm(agent_input, expect_json=True)

        try:
            parsed = self.parse_json_response(response)
        except Exception as e:
            logger.warning("Failed to parse dispatcher LLM response: %s, falling back to heuristic", e)
            return self._execute_stub(agent_input, output)

        # Ensure the parsed response has the expected structure
        classification = parsed.get("classification", {})
        plan = parsed.get("plan", {})

        # Guarantee required_agents is present and valid
        if not classification.get("required_agents"):
            classification["required_agents"] = self._infer_agents(agent_input)

        # Ensure plan has subtasks
        if not plan.get("subtasks"):
            plan = self._create_plan_from_classification(agent_input, classification)

        plan["run_id"] = agent_input.run_id

        output.status = TaskStatus.COMPLETED
        output.result = {
            "classification": classification,
            "plan": plan,
        }
        output.notes = (
            f"Dispatcher classified task via LLM ({self.llm_client.model_name}). "
            f"Type: {classification.get('task_type', 'unknown')}, "
            f"Agents: {classification.get('required_agents', [])}"
        )
        return output

    def _execute_stub(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Heuristic classification and planning (no LLM)."""
        classification = self._classify_task_heuristic(agent_input)
        plan = self._create_plan_from_classification(agent_input, classification)

        output.status = TaskStatus.COMPLETED
        output.result = {
            "classification": classification,
            "plan": plan,
        }
        output.notes = "Dispatcher classified task via heuristic (stub mode)."
        return output

    def _classify_task_heuristic(self, agent_input: AgentInput) -> dict:
        """Simple heuristic classification based on keywords."""
        description = agent_input.description.lower()

        if any(word in description for word in ["research", "compare", "investigate", "find"]):
            task_type = "research"
            required_agents = ["research"]
        elif any(word in description for word in ["build", "implement", "create", "scaffold"]):
            task_type = "build"
            required_agents = ["research", "builder", "reviewer"]
        elif any(word in description for word in ["fix", "bug", "repair", "patch"]):
            task_type = "fix"
            required_agents = ["builder", "reviewer"]
        elif any(word in description for word in ["review", "check", "audit", "verify"]):
            task_type = "review"
            required_agents = ["reviewer"]
        else:
            task_type = "multi-stage"
            required_agents = ["research", "builder", "reviewer"]

        criteria_count = len(agent_input.acceptance_criteria)
        if criteria_count <= 2:
            complexity = "simple"
        elif criteria_count <= 5:
            complexity = "moderate"
        else:
            complexity = "complex"

        return {
            "task_type": task_type,
            "complexity": complexity,
            "required_agents": required_agents,
            "estimated_subtasks": len(required_agents),
            "approval_level": agent_input.approval_level.value,
        }

    def _infer_agents(self, agent_input: AgentInput) -> list[str]:
        """Infer required agents from task description (fallback)."""
        classification = self._classify_task_heuristic(agent_input)
        return classification["required_agents"]

    def _create_plan_from_classification(self, agent_input: AgentInput, classification: dict) -> dict:
        """Create an execution plan with ordered subtasks."""
        subtasks = []
        for i, agent_name in enumerate(classification["required_agents"], start=1):
            subtask = {
                "id": i,
                "assigned_agent": agent_name,
                "description": f"{agent_name.title()} phase for: {agent_input.description}",
                "depends_on": [i - 1] if i > 1 else [],
                "approval_level": 0,
            }
            subtasks.append(subtask)

        return {
            "run_id": agent_input.run_id,
            "subtasks": subtasks,
            "execution_order": list(range(1, len(subtasks) + 1)),
        }

    def _skill_prefix(self) -> str:
        return "dispatch"
