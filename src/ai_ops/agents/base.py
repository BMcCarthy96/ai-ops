"""
Base agent class for AI Ops.

All agents inherit from BaseAgent. This provides a consistent interface
for the orchestration layer to interact with agents regardless of their
specialization.

Phase 2A: Agents accept an LLM client and use it for execution.
          If no client is provided (or StubClient is used), agents
          fall back to deterministic behavior for testing.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ai_ops.llm.client import LLMClient, StubClient, create_client
from ai_ops.llm.prompts import build_user_message, load_system_prompt

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Roles available in the AI Ops agent system."""

    DISPATCHER = "dispatcher"
    RESEARCH = "research"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    # Future agents — not implemented yet
    BROWSER_OPERATOR = "browser-operator"
    OPS_INTEGRATION = "ops-integration"
    COMMS = "comms"
    KNOWLEDGE = "knowledge"


class ApprovalLevel(int, Enum):
    """Approval levels for actions. See policies/approval-matrix.yaml."""

    AUTO = 0        # No approval needed
    SOFT = 1        # Can proceed, inform operator
    HARD = 2        # Must wait for operator approval
    BLOCKED = 3     # Forbidden by default


class TaskStatus(str, Enum):
    """Status of a task or subtask."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


class AgentInput(BaseModel):
    """Standard input structure for all agents."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    run_id: str = ""
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    assigned_by: str = ""
    approval_level: ApprovalLevel = ApprovalLevel.AUTO


class AgentOutput(BaseModel):
    """Standard output structure for all agents."""

    task_id: str = ""
    run_id: str = ""
    agent_role: str = ""
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    escalations: list[str] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    notes: str = ""


class BaseAgent(ABC):
    """
    Base class for all AI Ops agents.

    Each agent:
    - Has a defined role from AgentRole
    - Accepts AgentInput
    - Returns AgentOutput
    - Uses an LLM client for execution (or StubClient for tests)
    - Loads its system prompt from agents/{role}/prompt.md
    """

    def __init__(self, role: AgentRole, llm_client: LLMClient | None = None) -> None:
        self.role = role
        self.name = role.value
        self.llm_client = llm_client or StubClient()

        # Load system prompt from prompt.md
        try:
            self.system_prompt = load_system_prompt(self.name)
        except FileNotFoundError:
            logger.warning("No prompt.md found for %s, using empty prompt", self.name)
            self.system_prompt = f"You are the {self.name} agent."

    @property
    def is_stub_mode(self) -> bool:
        """True if using StubClient (no real LLM calls)."""
        return isinstance(self.llm_client, StubClient)

    def run(self, agent_input: AgentInput) -> AgentOutput:
        """
        Execute the agent's task.

        This is the main entry point for the orchestration layer.
        It handles timing, error catching, and delegates to the
        agent-specific `execute` method.
        """
        started_at = datetime.now(timezone.utc).isoformat()

        output = AgentOutput(
            task_id=agent_input.task_id,
            run_id=agent_input.run_id,
            agent_role=self.name,
            status=TaskStatus.IN_PROGRESS,
            started_at=started_at,
        )

        try:
            # Check if the agent needs approval before proceeding
            if agent_input.approval_level >= ApprovalLevel.HARD:
                output.status = TaskStatus.WAITING_APPROVAL
                output.notes = (
                    f"Requires Level {agent_input.approval_level.value} approval "
                    f"before {self.name} can proceed."
                )
                return output

            # Delegate to the agent-specific implementation
            output = self.execute(agent_input, output)

        except Exception as e:
            output.status = TaskStatus.FAILED
            output.issues.append(f"Agent {self.name} failed: {str(e)}")
            output.escalations.append(
                f"Unhandled error in {self.name}. Escalate to dispatcher."
            )
            logger.exception("Agent %s failed", self.name)

        output.completed_at = datetime.now(timezone.utc).isoformat()
        return output

    def call_llm(self, agent_input: AgentInput, expect_json: bool = True) -> str:
        """
        Build the user message and call the LLM.

        This is a convenience method used by agent execute() implementations.

        Args:
            agent_input: The task input to format as the user message.
            expect_json: Whether to request JSON output from the LLM.

        Returns:
            The raw LLM response string.
        """
        user_message = build_user_message(
            description=agent_input.description,
            context=agent_input.context,
            acceptance_criteria=agent_input.acceptance_criteria,
            constraints=agent_input.constraints,
        )

        logger.info(
            "Agent %s calling LLM (provider=%s, model=%s)",
            self.name,
            self.llm_client.provider_name,
            self.llm_client.model_name,
        )

        return self.llm_client.complete(
            system=self.system_prompt,
            user=user_message,
            expect_json=expect_json,
        )

    def parse_json_response(self, response: str) -> dict[str, Any]:
        """
        Parse a JSON response from the LLM.

        Handles three common LLM output patterns:
        1. Pure JSON: {"key": "value"}
        2. Markdown fence: ```json\\n{...}\\n```
        3. Prose prefix: "Here is the summary:\\n\\n{...}"

        Raises:
            json.JSONDecodeError: If no valid JSON object is found after all
                extraction attempts.
        """
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Fast path: already a bare JSON object or array
        if text.startswith(("{", "[")):
            return json.loads(text)

        # Slow path: prose prefix — extract the outermost {...} block.
        # Handles "Here is the summary:\n\n{...}" style responses that the
        # model sometimes produces on larger tasks despite being instructed
        # to output JSON only.
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass  # greedy match captured too much; fall through

        # Nothing parseable — raise with the original text so callers can log it
        return json.loads(text)

    @abstractmethod
    def execute(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """
        Agent-specific execution logic.

        Subclasses implement this method with their specialized behavior.
        """
        ...

    def can_handle(self, skill_name: str) -> bool:
        """Check if this agent can handle a given skill."""
        return skill_name.startswith(self._skill_prefix())

    @abstractmethod
    def _skill_prefix(self) -> str:
        """Return the skill category prefix this agent handles."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(role={self.name}, provider={self.llm_client.provider_name})>"
