"""
Research Agent — Information gathering and analysis for AI Ops.

The Research agent investigates topics, compares options, extracts requirements,
and produces structured research reports.

Uses LLM to perform real analysis. Falls back to stub output in stub mode.
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


class ResearchAgent(BaseAgent):
    """
    Information gathering and analysis agent.

    Responsibilities:
    - Research tools, docs, APIs, and constraints
    - Compare options with structured criteria
    - Extract requirements from specifications
    - Produce structured research reports
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        super().__init__(AgentRole.RESEARCH, llm_client)

    def execute(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Execute a research task using LLM or stub."""
        if self.is_stub_mode:
            return self._execute_stub(agent_input, output)

        return self._execute_llm(agent_input, output)

    def _execute_llm(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """LLM-powered research."""
        response = self.call_llm(agent_input, expect_json=True)

        try:
            parsed = self.parse_json_response(response)
        except Exception as e:
            logger.warning("Failed to parse research LLM response: %s", e)
            # Store raw response as the result
            parsed = {
                "research_question": agent_input.description,
                "findings": [{"id": 1, "finding": response, "evidence": "raw LLM output", "confidence": "medium"}],
                "assumptions": [],
                "recommendations": {"recommended": "Review raw output", "alternatives": []},
                "gaps": ["Response was not structured JSON"],
                "parse_error": str(e),
            }

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = f"Research completed via LLM ({self.llm_client.model_name})."
        return output

    def _execute_stub(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Deterministic stub output for testing."""
        output.status = TaskStatus.COMPLETED
        output.result = {
            "research_question": agent_input.description,
            "scope": {
                "included": agent_input.constraints or ["Full scope as described"],
                "excluded": [],
            },
            "findings": [
                {
                    "id": 1,
                    "finding": f"Research findings for: {agent_input.description}",
                    "evidence": "Stub mode — no real research performed",
                    "confidence": "n/a",
                }
            ],
            "assumptions": ["Stub mode active"],
            "recommendations": {
                "recommended": "Proceed with standard approach",
                "alternatives": [],
            },
            "gaps": [],
        }
        output.notes = "Research agent completed in stub mode."
        return output

    def _skill_prefix(self) -> str:
        return "research"
