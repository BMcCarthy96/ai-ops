"""
LLM Client — Provider abstraction for AI Ops.

Defines a simple protocol for LLM calls and provides two implementations:
- AnthropicClient: Real LLM calls via the Anthropic SDK
- StubClient: Deterministic responses for tests and dry runs

Usage:
    from ai_ops.llm.client import create_client

    # Auto-detects: uses Anthropic if ANTHROPIC_API_KEY is set, else Stub
    client = create_client()
    response = client.complete(
        system="You are a helpful assistant.",
        user="What is 2+2?",
    )
"""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM providers. Implement this to add a new provider."""

    @property
    def provider_name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    def model_name(self) -> str:
        """Model identifier being used."""
        ...

    def complete(self, system: str, user: str, expect_json: bool = False) -> str:
        """
        Send a completion request to the LLM.

        Args:
            system: System prompt text.
            user: User message text.
            expect_json: If True, hint to the model to return valid JSON.

        Returns:
            The model's response text.
        """
        ...


class AnthropicClient:
    """
    LLM client using the Anthropic Python SDK directly.

    Requires:
        pip install anthropic
        ANTHROPIC_API_KEY environment variable

    Optional env vars:
        ANTHROPIC_MODEL: Model to use (default: claude-sonnet-4-20250514)
        ANTHROPIC_MAX_TOKENS: Max response tokens (default: 4096)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "The 'anthropic' package is required. Install with: pip install anthropic"
            ) from e

        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set as an environment variable "
                "or passed directly to AnthropicClient."
            )

        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._max_tokens = max_tokens or int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))
        self._client = anthropic.Anthropic(api_key=self._api_key)

        logger.info("AnthropicClient initialized: model=%s, max_tokens=%d", self._model, self._max_tokens)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system: str, user: str, expect_json: bool = False) -> str:
        """Send a completion request to the Anthropic API."""
        user_msg = user
        if expect_json:
            user_msg += "\n\nRespond with valid JSON only. No markdown fences, no commentary."

        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        # Extract text from the response
        response_text = ""
        for block in message.content:
            if block.type == "text":
                response_text += block.text

        logger.debug(
            "Anthropic response: model=%s, input_tokens=%d, output_tokens=%d",
            message.model,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )

        return response_text


class StubClient:
    """
    Deterministic LLM client for tests and dry runs.

    Returns canned JSON responses that match each agent's expected output
    structure. Used when no API key is available or during testing.
    """

    # Canned responses keyed by keywords found in the system prompt.
    # This lets each agent get a response that matches its output schema.
    _RESPONSES: dict[str, dict] = {
        "dispatcher": {
            "classification": {
                "task_type": "multi-stage",
                "complexity": "moderate",
                "estimated_subtasks": 3,
                "required_agents": ["research", "builder", "reviewer"],
                "required_skills": ["research.analyze.codebase", "coding.implement.feature", "qa.review.implementation"],
                "approval_level": 0,
                "urgency": "normal",
                "risks": ["Scope may be underestimated"],
            },
            "plan": {
                "subtasks": [
                    {"id": 1, "description": "Research phase", "assigned_agent": "research", "depends_on": []},
                    {"id": 2, "description": "Build phase", "assigned_agent": "builder", "depends_on": [1]},
                    {"id": 3, "description": "Review phase", "assigned_agent": "reviewer", "depends_on": [2]},
                ],
                "execution_order": [1, 2, 3],
            },
        },
        "research": {
            "research_question": "As specified in the task",
            "findings": [
                {"id": 1, "finding": "Key finding from research", "evidence": "Based on analysis", "confidence": "high"},
            ],
            "assumptions": ["Standard environment assumed"],
            "recommendations": {"recommended": "Proceed with the standard approach", "alternatives": []},
            "constraints": [],
            "risks": [],
            "gaps": [],
        },
        "builder": {
            "implementation_summary": "Implementation completed as planned",
            "files_changed": {"created": ["module.py", "test_module.py"], "modified": [], "deleted": []},
            "tests_created": ["test_module.py"],
            "dependencies_added": [],
            "deviations_from_plan": "none",
            "known_limitations": [],
        },
        "reviewer": {
            "verdict": "PASS",
            "verdict_reason": "All acceptance criteria met",
            "acceptance_criteria": [],
            "findings": [],
            "policy_compliance": {"security_rules": "pass", "naming_conventions": "pass", "data_handling": "pass"},
            "plan_adherence": "yes",
            "missing_items": [],
            "recommendation": "Approve for merge",
        },
    }

    def __init__(self) -> None:
        logger.info("StubClient initialized (no LLM calls will be made)")

    @property
    def provider_name(self) -> str:
        return "stub"

    @property
    def model_name(self) -> str:
        return "stub-v1"

    def complete(self, system: str, user: str, expect_json: bool = False) -> str:
        """Return a canned response based on which agent is calling."""
        system_lower = system.lower()

        for agent_key, response in self._RESPONSES.items():
            if agent_key in system_lower:
                return json.dumps(response)

        # Fallback: generic response
        return json.dumps({"status": "completed", "result": "Stub response"})


def create_client(api_key: str | None = None) -> LLMClient:
    """
    Factory: create the appropriate LLM client.

    If ANTHROPIC_API_KEY is set (or passed), returns AnthropicClient.
    Otherwise, returns StubClient for dry-run / test mode.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        try:
            return AnthropicClient(api_key=key)
        except ImportError:
            logger.warning("anthropic package not installed, falling back to StubClient")
            return StubClient()
    else:
        logger.info("No ANTHROPIC_API_KEY found, using StubClient")
        return StubClient()
