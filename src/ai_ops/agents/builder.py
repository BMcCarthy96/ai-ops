"""
Builder Agent — Implementation and code creation for AI Ops.

The Builder agent implements approved plans by writing code, scaffolding
projects, and producing implementation artifacts in isolated worktrees.

Uses LLM to generate implementation plans and code suggestions.
Falls back to stub output in stub mode.
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


class BuilderAgent(BaseAgent):
    """
    Implementation and code creation agent.

    Responsibilities:
    - Implement approved plans
    - Scaffold new services and modules
    - Write code in isolated worktrees
    - Produce implementation notes
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        super().__init__(AgentRole.BUILDER, llm_client)

    def execute(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Execute a build task using LLM or stub."""
        if self.is_stub_mode:
            return self._execute_stub(agent_input, output)

        return self._execute_llm(agent_input, output)

    def _execute_llm(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """LLM-powered implementation planning."""
        response = self.call_llm(agent_input, expect_json=True)

        try:
            parsed = self.parse_json_response(response)
        except Exception as e:
            logger.warning("Failed to parse builder LLM response: %s", e)
            parsed = {
                "implementation_summary": response,
                "files_changed": {"created": [], "modified": [], "deleted": []},
                "tests_created": [],
                "dependencies_added": [],
                "deviations_from_plan": "none",
                "known_limitations": [],
                "parse_error": str(e),
            }

        # Ensure research context is acknowledged
        research_context = agent_input.context.get("research_output", {})
        parsed["research_context_received"] = bool(research_context)

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = f"Builder completed via LLM ({self.llm_client.model_name})."
        return output

    def _execute_stub(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Deterministic stub output for testing."""
        research_context = agent_input.context.get("research_output", {})

        output.status = TaskStatus.COMPLETED
        output.result = {
            "implementation_summary": f"Build phase for: {agent_input.description}",
            "research_context_received": bool(research_context),
            "files_changed": {
                "created": [],
                "modified": [],
                "deleted": [],
            },
            "tests_created": [],
            "dependencies_added": [],
            "branch": f"ai-ops/builder/{agent_input.run_id}/implement",
            "worktree": f"../worktrees/{agent_input.run_id}/",
            "deviations_from_plan": "none",
        }
        output.notes = "Builder agent completed in stub mode."
        return output

    def _skill_prefix(self) -> str:
        return "coding"
