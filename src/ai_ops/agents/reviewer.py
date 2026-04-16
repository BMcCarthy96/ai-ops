"""
Reviewer Agent — Quality assurance and validation for AI Ops.

The Reviewer agent reviews implementations, runs checks, identifies regressions,
and produces structured review reports with pass/fail verdicts.

LLM mode: uses a bounded tool-call loop (run_ruff / run_mypy / run_pytest /
read_file) so the model calls and interprets checks directly rather than
reasoning over pre-injected results. Falls back to a single-shot call when no
worktree is available or when the client does not support tool use.

Stub mode: deterministic output for tests.
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
from ai_ops.tools.shell_tools import ShellResult, ShellTools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schemas — Anthropic tool-use format
# ---------------------------------------------------------------------------

_REVIEWER_TOOLS: list[dict] = [
    {
        "name": "run_ruff",
        "description": (
            "Run ruff lint check on the builder's deliverable files. "
            "Omit paths to default to the files written by the builder."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific paths to check. "
                        "Omit to use the builder's files_written list."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_mypy",
        "description": (
            "Run mypy type check on the builder's Python files. "
            "Omit paths to default to .py files from files_written."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific .py paths to check. "
                        "Omit to use .py files from files_written."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_pytest",
        "description": (
            "Run pytest on test files written by the builder. "
            "Omit paths to default to test_*.py / *_test.py files from files_written."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific test file paths to run. "
                        "Omit to use test files from files_written."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the worktree to inspect its content.",
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
]


def _fmt_shell(r: ShellResult) -> str:
    """Format a ShellResult as a string for the LLM tool result."""
    out = (r.stdout + r.stderr).strip()
    return f"returncode={r.returncode}\n{out}" if out else f"returncode={r.returncode}"


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
        """Tool-call loop: Reviewer calls checks directly and synthesises verdict."""
        build_output = agent_input.context.get("build_output", {})
        _files_changed = build_output.get("files_changed", {}) if isinstance(build_output, dict) else {}
        _created = _files_changed.get("created", []) if isinstance(_files_changed, dict) else []
        _modified = _files_changed.get("modified", []) if isinstance(_files_changed, dict) else []
        files_written: list[str] = [f for f in (_created + _modified) if isinstance(f, str)]

        file_tools = FileTools(Path(worktree_path_str))
        shell = ShellTools(Path(worktree_path_str))

        # Pre-run automated checks and inject results into context.
        # Reduces API roundtrips from ~6 to 1-3: the model receives ruff/mypy/pytest
        # results upfront and only needs read_file for optional deeper inspection.
        pre_check_results: dict = {}
        if files_written:
            try:
                pre_check_results = self._run_automated_checks(
                    worktree_path_str, files_written=files_written
                )
            except Exception as exc:
                logger.warning("Reviewer pre-flight checks failed: %s", exc)

        if pre_check_results:
            agent_input = agent_input.model_copy(update={
                "context": {
                    **agent_input.context,
                    "automated_checks_results": pre_check_results,
                }
            })
            # Checks are in context — only read_file is needed in the loop
            loop_tools = [t for t in _REVIEWER_TOOLS if t["name"] == "read_file"]
        else:
            # No files or pre-run failed — fall back to full tool set
            loop_tools = _REVIEWER_TOOLS

        def tool_executor(name: str, inputs: dict) -> str:
            if name == "run_ruff":
                paths = inputs.get("paths") or (files_written if files_written else None)
                if not paths:
                    return "returncode=0\n(no files to check)"
                return _fmt_shell(shell.run_ruff(paths=paths))

            if name == "run_mypy":
                requested = inputs.get("paths")
                if requested:
                    py_files = [f for f in requested if f.endswith(".py")]
                else:
                    py_files = [f for f in files_written if f.endswith(".py")]
                if not py_files:
                    return "returncode=0\n(no Python files to check)"
                return _fmt_shell(shell.run_mypy(paths=py_files))

            if name == "run_pytest":
                requested = inputs.get("paths")
                if requested:
                    test_files = requested
                else:
                    test_files = [
                        f for f in files_written
                        if Path(f).name.startswith("test_")
                        or Path(f).name.endswith("_test.py")
                    ]
                if not test_files:
                    return "returncode=0\n(no test files in deliverable — skipped)"
                return _fmt_shell(shell.run_pytest(paths=test_files))

            if name == "read_file":
                try:
                    return file_tools.read_file(inputs["path"])
                except FileNotFoundError:
                    return f"(file not found: {inputs['path']})"
                except Exception as exc:
                    return f"(error reading {inputs['path']}: {exc})"

            return f"unknown tool: {name}"

        user_message = build_user_message(
            description=agent_input.description,
            context=agent_input.context,
            acceptance_criteria=agent_input.acceptance_criteria,
            constraints=agent_input.constraints,
        )

        final_text, tool_log = self.llm_client.complete_with_tools(
            system=self.system_prompt,
            user=user_message,
            tools=loop_tools,
            tool_executor=tool_executor,
            max_iterations=8,
        )

        try:
            parsed = self.parse_json_response(final_text)
        except Exception as e:
            logger.warning("Failed to parse reviewer tool-loop response: %s", e)
            parsed = {
                "verdict": "PASS WITH ISSUES",
                "verdict_reason": f"Review completed but response parsing failed: {e}",
                "raw_review": final_text,
                "acceptance_criteria": [],
                "findings": [],
                "policy_compliance": {},
                "recommendation": "Manual review recommended due to parse error",
            }

        if "verdict" not in parsed:
            parsed["verdict"] = "PASS WITH ISSUES"
            parsed["verdict_reason"] = "No explicit verdict in LLM response"

        parsed["build_context_received"] = bool(build_output)
        parsed["tool_call_count"] = len(tool_log)

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = (
            f"Reviewer completed via LLM tool loop ({self.llm_client.model_name}). "
            f"{len(tool_log)} tool call(s)."
        )
        return output

    def _execute_llm_oneshot(
        self, agent_input: AgentInput, output: AgentOutput
    ) -> AgentOutput:
        """One-shot JSON: used when no worktree or client lacks tool support.

        Preserves the original pre-injection behaviour: runs automated checks
        first, injects results into context, then makes a single LLM call.
        """
        worktree_path_str = agent_input.context.get("worktree_path", "")
        check_results: dict = {}
        if worktree_path_str:
            try:
                build_output = agent_input.context.get("build_output", {})
                _files_changed = build_output.get("files_changed", {}) if isinstance(build_output, dict) else {}
                _created = _files_changed.get("created", []) if isinstance(_files_changed, dict) else []
                _modified = _files_changed.get("modified", []) if isinstance(_files_changed, dict) else []
                files_written: list[str] = [f for f in (_created + _modified) if isinstance(f, str)]
                check_results = self._run_automated_checks(
                    worktree_path_str, files_written=files_written
                )
            except Exception as exc:
                logger.warning("Automated checks failed: %s", exc)

        if check_results:
            enriched_input = agent_input.model_copy(update={
                "context": {
                    **agent_input.context,
                    "automated_checks_results": check_results,
                }
            })
        else:
            enriched_input = agent_input

        response = self.call_llm(enriched_input, expect_json=True)

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

        if "verdict" not in parsed:
            parsed["verdict"] = "PASS WITH ISSUES"
            parsed["verdict_reason"] = "No explicit verdict in LLM response"

        build_context = agent_input.context.get("build_output", {})
        parsed["build_context_received"] = bool(build_context)

        output.status = TaskStatus.COMPLETED
        output.result = parsed
        output.notes = f"Reviewer completed via LLM one-shot ({self.llm_client.model_name})."
        return output

    # ------------------------------------------------------------------
    # One-shot helper: pre-run checks and inject into context
    # ------------------------------------------------------------------

    def _run_automated_checks(
        self, worktree_path_str: str, files_written: list[str] | None = None
    ) -> dict:
        """
        Run ruff, mypy, and (optionally) pytest against the builder's deliverable.

        Scope: only files listed in files_written. Returns {} when files_written
        is absent or empty so no checks are injected. Checking "." is avoided.
        """
        if not files_written:
            logger.info("Reviewer: no files_written provided — skipping automated checks")
            return {}

        py_files = [f for f in files_written if f.endswith(".py")]
        if not py_files:
            logger.info("Reviewer: no Python files in files_written — skipping checks")
            return {}

        worktree = Path(worktree_path_str)
        shell = ShellTools(worktree)

        ruff = shell.run_ruff(paths=py_files)
        mypy = shell.run_mypy(paths=py_files)

        results: dict = {
            "ruff": {
                "status": ruff.status,
                "returncode": ruff.returncode,
                "output": (ruff.stdout + ruff.stderr).strip(),
            },
            "mypy": {
                "status": mypy.status,
                "returncode": mypy.returncode,
                "output": (mypy.stdout + mypy.stderr).strip(),
            },
        }

        test_files = [
            f for f in py_files
            if Path(f).name.startswith("test_") or Path(f).name.endswith("_test.py")
        ]
        if test_files:
            pytest_result = shell.run_pytest(paths=test_files)
            results["pytest"] = {
                "status": pytest_result.status,
                "returncode": pytest_result.returncode,
                "output": (pytest_result.stdout + pytest_result.stderr).strip(),
            }

        return results

    # ------------------------------------------------------------------
    # Stub path
    # ------------------------------------------------------------------

    def _execute_stub(self, agent_input: AgentInput, output: AgentOutput) -> AgentOutput:
        """Deterministic stub output for testing."""
        build_context = agent_input.context.get("build_output", {})

        criteria_results = []
        for i, criterion in enumerate(agent_input.acceptance_criteria, start=1):
            criteria_results.append({
                "id": i,
                "criterion": criterion,
                "status": "PASS",
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
