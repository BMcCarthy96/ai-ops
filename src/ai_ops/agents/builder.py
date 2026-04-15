"""
Builder Agent — Implementation and code creation for AI Ops.

The Builder agent implements approved plans by writing code, scaffolding
projects, and producing implementation artifacts in isolated worktrees.

LLM mode: uses a bounded tool-call loop (write_file / read_file / list_files)
so the model can iteratively write files and verify their content. Falls back
to a single-shot JSON call when no worktree is available or when the client
does not support tool use.

Stub mode: deterministic output for tests; file writing via code_output dict.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai_ops.agents.base import (
    AgentInput,
    AgentOutput,
    AgentRole,
    BaseAgent,
    TaskStatus,
)
from ai_ops.llm.client import LLMClient
from ai_ops.llm.prompts import build_user_message
from ai_ops.tools.file_tools import FileTools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas — Anthropic tool-use format
# ---------------------------------------------------------------------------

_BUILDER_TOOLS: list[dict] = [
    {
        "name": "write_file",
        "description": (
            "Write a file to the worktree. Creates parent directories as needed. "
            "Call this once per file with the complete file content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path relative to the worktree root "
                        "(e.g., 'arithmetic_ops/add.py', 'tests/test_add.py')"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Complete file content as a string.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read an existing file from the worktree.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to the worktree root.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a worktree directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory relative to the worktree root (default: '.').",
                },
            },
            "required": [],
        },
    },
]


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

    # ------------------------------------------------------------------
    # Placeholder / underspecified task detection
    # ------------------------------------------------------------------

    _PLACEHOLDER_PREFIXES = ("builder phase for:",)
    _PLACEHOLDER_BODIES = {"...", "…", "placeholder", "tbd", "todo", "n/a", ""}

    @classmethod
    def _is_placeholder_description(cls, description: str) -> bool:
        """Return True when the description is a dispatcher-generated placeholder.

        Catches two cases:
        - Empty or whitespace-only description.
        - Template strings produced by dispatchers that fail to fill in the
          task detail, e.g. "Builder phase for: ..." or "Builder phase for: ".
        """
        stripped = description.strip()
        if not stripped:
            return True
        lower = stripped.lower()
        for prefix in cls._PLACEHOLDER_PREFIXES:
            if lower.startswith(prefix):
                remainder = lower[len(prefix):].strip()
                if remainder in cls._PLACEHOLDER_BODIES or len(remainder) < 4:
                    return True
        return False

    def _escalate_underspecified(
        self, agent_input: AgentInput, output: AgentOutput
    ) -> AgentOutput:
        """Return an ESCALATED output immediately, writing no files."""
        msg = (
            "Task description is a placeholder or incomplete. "
            "Builder cannot implement without a concrete specification. "
            f"Received: {agent_input.description!r}"
        )
        output.status = TaskStatus.ESCALATED
        output.result = {
            "escalation_reason": msg,
            "description_received": agent_input.description,
            "required": "Provide a specific task description with concrete requirements.",
            "files_written": [],
        }
        output.escalations.append(
            "Underspecified task — escalate to dispatcher for a concrete specification."
        )
        output.notes = "Builder escalated: task description is a placeholder or empty."
        logger.warning("Builder escalating: placeholder description %r", agent_input.description)
        return output

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Execute a build task using LLM or stub.

        Pre-flight: if the task description is a placeholder, escalate immediately
        without writing any files or calling any tools.

        LLM path: files are written inside _execute_llm (either via the tool-call
        loop or via _write_code_to_worktree for the one-shot fallback).
        Stub path: _execute_stub populates code_output; _write_code_to_worktree
        writes those files to the worktree afterwards.
        """
        if self._is_placeholder_description(agent_input.description):
            return self._escalate_underspecified(agent_input, output)

        if self.is_stub_mode:
            output = self._execute_stub(agent_input, output)
            # Stub: write code_output dict to worktree the old way
            if output.status == TaskStatus.COMPLETED:
                self._write_code_to_worktree(agent_input, output)
        else:
            output = self._execute_llm(agent_input, output)

        return output

    # ------------------------------------------------------------------
    # LLM execution paths
    # ------------------------------------------------------------------

    def _execute_llm(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Route to tool-call loop or one-shot JSON depending on context."""
        worktree_path_str = agent_input.context.get("worktree_path", "")

        if worktree_path_str and hasattr(self.llm_client, "complete_with_tools"):
            return self._execute_llm_with_tools(agent_input, output, worktree_path_str)

        return self._execute_llm_oneshot(agent_input, output)

    def _execute_llm_with_tools(
        self,
        agent_input: AgentInput,
        output: AgentOutput,
        worktree_path_str: str,
    ) -> AgentOutput:
        """Tool-call loop: builder writes files directly via write_file calls."""
        file_tools = FileTools(Path(worktree_path_str))
        files_written: list[str] = []

        def _normalize(content: str) -> str:
            """Strip trailing whitespace per line; ensure single trailing newline."""
            lines = [line.rstrip() for line in content.splitlines()]
            return "\n".join(lines) + "\n"

        def tool_executor(name: str, inputs: dict) -> str:
            if name == "write_file":
                file_tools.write_file(inputs["path"], _normalize(inputs["content"]))
                files_written.append(inputs["path"])
                return f"wrote {inputs['path']}"
            if name == "read_file":
                return file_tools.read_file(inputs["path"])
            if name == "list_files":
                result = file_tools.list_files(inputs.get("directory", "."))
                return "\n".join(result) if result else "(empty)"
            return f"unknown tool: {name}"

        user_message = build_user_message(
            description=agent_input.description,
            context=agent_input.context,
            acceptance_criteria=agent_input.acceptance_criteria,
            constraints=agent_input.constraints,
        )

        final_text, tool_call_log = self.llm_client.complete_with_tools(
            system=self.system_prompt,
            user=user_message,
            tools=_BUILDER_TOOLS,
            tool_executor=tool_executor,
            max_iterations=10,
        )

        # Parse JSON summary from the model's final text
        try:
            parsed = self.parse_json_response(final_text)
        except Exception as e:
            logger.warning("Failed to parse builder tool-loop response: %s", e)
            parsed = {
                "implementation_summary": final_text or "Implementation via tool loop",
                "files_changed": {
                    "created": files_written,
                    "modified": [],
                    "deleted": [],
                },
                "tests_created": [],
                "dependencies_added": [],
                "deviations_from_plan": "none",
                "known_limitations": [f"JSON parse error: {e}"],
            }

        research_context = agent_input.context.get("research_output", {})
        parsed["research_context_received"] = bool(research_context)
        parsed["files_written"] = files_written
        parsed["tool_call_count"] = len(tool_call_log)

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = (
            f"Builder completed via LLM tool loop ({self.llm_client.model_name}). "
            f"{len(files_written)} file(s) written, {len(tool_call_log)} tool call(s)."
        )
        return output

    def _execute_llm_oneshot(
        self, agent_input: AgentInput, output: AgentOutput
    ) -> AgentOutput:
        """Single-shot JSON: used when no worktree or client lacks tool support."""
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

        research_context = agent_input.context.get("research_output", {})
        parsed["research_context_received"] = bool(research_context)

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = f"Builder completed via LLM one-shot ({self.llm_client.model_name})."

        # Write any code_output files if present (backward-compat for one-shot mode)
        if output.status == TaskStatus.COMPLETED:
            self._write_code_to_worktree(agent_input, output)

        return output

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _write_code_to_worktree(
        self, agent_input: AgentInput, output: AgentOutput
    ) -> None:
        """Write code_output dict to worktree if worktree_path is in context.

        Used by stub mode and the one-shot LLM fallback. The tool-call loop
        writes files directly, so this is a no-op for that path.
        """
        worktree_path_str = agent_input.context.get("worktree_path", "")
        code_output = output.result.get("code_output", {})
        if not (worktree_path_str and isinstance(code_output, dict) and code_output):
            return

        file_tools = FileTools(Path(worktree_path_str))
        files_written: list[str] = []
        write_errors: list[str] = []
        for rel_path, content in code_output.items():
            try:
                file_tools.write_file(rel_path, str(content))
                files_written.append(rel_path)
            except Exception as exc:
                logger.warning("Failed to write %s to worktree: %s", rel_path, exc)
                write_errors.append(f"{rel_path}: {exc}")

        output.result["files_written"] = files_written
        if write_errors:
            output.result["write_errors"] = write_errors
        logger.info(
            "Builder wrote %d file(s) to worktree %s",
            len(files_written),
            worktree_path_str,
        )

    # ------------------------------------------------------------------
    # Stub path
    # ------------------------------------------------------------------

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
