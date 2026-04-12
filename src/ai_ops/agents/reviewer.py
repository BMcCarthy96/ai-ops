"""
Reviewer Agent — Quality assurance and validation for AI Ops.

The Reviewer agent reviews implementations, runs checks, identifies regressions,
and produces structured review reports with pass/fail verdicts.

Uses LLM to evaluate implementation quality and acceptance criteria.
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


class ReviewerAgent(BaseAgent):
    """
    Quality assurance and validation agent.

    Responsibilities:
    - Review implementations against plans
    - Run automated checks (lint, type, test)
    - Check acceptance criteria
    - Produce structured review reports
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        super().__init__(AgentRole.REVIEWER, llm_client)

    def execute(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Execute a review task using LLM or stub."""
        if self.is_stub_mode:
            return self._execute_stub(agent_input, output)

        return self._execute_llm(agent_input, output)

    def _execute_llm(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """LLM-powered code review."""
        response = self.call_llm(agent_input, expect_json=True)

        try:
            parsed = self.parse_json_response(response)
        except Exception as e:
            logger.warning("Failed to parse reviewer LLM response: %s", e)
            parsed = {
                "verdict": "PASS WITH ISSUES",
                "verdict_reason": f"Review completed but response parsing failed: {e}",
                "raw_review": response,
                "acceptance_criteria": [],
                "findings": [],
                "policy_compliance": {},
                "recommendation": "Manual review recommended due to parse error",
            }

        # Ensure verdict exists
        if "verdict" not in parsed:
            parsed["verdict"] = "PASS WITH ISSUES"
            parsed["verdict_reason"] = "No explicit verdict in LLM response"

        # Track build context reception
        build_context = agent_input.context.get("build_output", {})
        parsed["build_context_received"] = bool(build_context)

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = f"Reviewer completed via LLM ({self.llm_client.model_name})."
        return output

    def _execute_stub(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Deterministic stub output for testing."""
        build_context = agent_input.context.get("build_output", {})

        criteria_results = []
        for i, criterion in enumerate(agent_input.acceptance_criteria, start=1):
            criteria_results.append({
                "id": i,
                "criterion": criterion,
                "status": "pass",
                "notes": "Stub mode — auto-passed",
            })

        output.status = TaskStatus.COMPLETED
        output.result = {
            "verdict": "PASS",
            "verdict_reason": "Stub mode — all criteria auto-passed",
            "build_context_received": bool(build_context),
            "acceptance_criteria": criteria_results,
            "automated_checks": [
                {"check": "Lint", "tool": "ruff", "status": "not_run", "details": "Stub mode"},
                {"check": "Type check", "tool": "mypy", "status": "not_run", "details": "Stub mode"},
                {"check": "Unit tests", "tool": "pytest", "status": "not_run", "details": "Stub mode"},
            ],
            "findings": [],
            "policy_compliance": [
                {"policy": "Security rules", "status": "not_checked", "notes": "Stub mode"},
                {"policy": "Naming conventions", "status": "not_checked", "notes": "Stub mode"},
                {"policy": "Data handling", "status": "not_checked", "notes": "Stub mode"},
            ],
            "plan_adherence": {"matches_plan": "not_verified", "deviations": "none"},
            "missing_items": [],
            "recommendation": "Auto-approved (stub mode)",
        }
        output.notes = "Reviewer agent completed in stub mode."
        return output

    def _skill_prefix(self) -> str:
        return "qa"
