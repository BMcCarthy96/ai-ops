"""
Prompt loading and message building for AI Ops agents.

Reads agent prompt.md files and formats AgentInput into structured
user messages for the LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Resolve the repo root (ai-ops/) relative to this file's location
_REPO_ROOT = Path(__file__).resolve().parents[3]


def load_system_prompt(agent_role: str) -> str:
    """
    Load the system prompt for an agent from its prompt.md file.

    Args:
        agent_role: The agent role name (e.g., "dispatcher", "research").

    Returns:
        The full text of the prompt.md file.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    prompt_path = _REPO_ROOT / "agents" / agent_role / "prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def build_user_message(
    description: str,
    context: dict[str, Any] | None = None,
    acceptance_criteria: list[str] | None = None,
    constraints: list[str] | None = None,
) -> str:
    """
    Build a structured user message from task parameters.

    Formats all inputs into a clear, structured message that the LLM
    can parse reliably. Uses a simple text format, not JSON, so the
    LLM has natural context to work with.

    Args:
        description: The task description.
        context: Optional context dict (e.g., research output, build output).
        acceptance_criteria: Optional list of acceptance criteria.
        constraints: Optional list of constraints.

    Returns:
        A formatted user message string.
    """
    parts = [f"## Task\n{description}"]

    if acceptance_criteria:
        criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria)
        parts.append(f"## Acceptance Criteria\n{criteria_text}")

    if constraints:
        constraints_text = "\n".join(f"- {c}" for c in constraints)
        parts.append(f"## Constraints\n{constraints_text}")

    if context:
        # Serialize context to readable JSON for the LLM
        for key, value in context.items():
            if value:  # skip empty context
                context_json = json.dumps(value, indent=2, default=str)
                parts.append(f"## Context: {key}\n```json\n{context_json}\n```")

    return "\n\n".join(parts)
