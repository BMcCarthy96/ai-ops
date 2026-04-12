# AI Ops — Agent Transition Handoff

> **Date:** 2026-04-12  
> **Phase:** 2A complete. Phase 2B not started.  
> **Repo root:** `C:\Users\user\.gemini\antigravity\scratch\ai-ops`  
> **Source of truth:** The repo files. This document is an index, not a replacement.

---

## 1. Project Purpose

AI Ops is an internal multi-agent operations system. A human operator submits tasks through a Dispatcher agent that classifies, plans, delegates to specialist agents (Research → Builder → Reviewer), and consolidates results. Agents have explicit roles, policies, approval levels, and produce structured output persisted to disk.

**It is not** a chatbot, a SaaS product, or a generic framework. It is an operator-directed execution system.

---

## 2. Architecture

```
Operator → CLI (cli.py)
                │
                ▼
         LangGraph Pipeline (dispatch_pipeline.py)
                │
    init → dispatcher → approval_gate → research → builder → reviewer → persist
                                            │
                                            ▼
                                     [skip to persist if denied/blocked]
```

**Core boundary rules:**
- `agents/` = human-readable YAML/MD definitions (roles, policies, prompts, tools). NOT code.
- `src/ai_ops/` = all executable Python. Agents, LLM client, runtime (approval, persistence).
- `workflows/langgraph/` = LangGraph graph definition, state, schemas.
- `policies/` = governance YAML. Approval matrix, security, data, naming, escalation.
- `memory/` = run summaries and decision records (YAML, written by persistence module).
- `runs/` = per-run directories (active → completed | failed).

**LLM abstraction:** `LLMClient` protocol → two implementations:
- `AnthropicClient` (real, uses `anthropic` SDK directly — no LangChain)
- `StubClient` (deterministic canned responses for tests)

`create_client()` factory auto-selects based on `ANTHROPIC_API_KEY` env var.

---

## 3. What Is Implemented (Working, Tested)

| Component | Detail |
|-----------|--------|
| 4 agent classes | `DispatcherAgent`, `ResearchAgent`, `BuilderAgent`, `ReviewerAgent` — all with dual LLM/stub execution |
| `BaseAgent` | Abstract base with `run()` envelope, `call_llm()`, `parse_json_response()`, approval check, prompt loading |
| `LLMClient` protocol | `AnthropicClient` + `StubClient` + `create_client()` factory |
| `prompts.py` | `load_system_prompt()` from `agents/{role}/prompt.md`, `build_user_message()` |
| `ApprovalHandler` protocol | `InteractiveApprovalHandler` (stdin) + `AutoApprovalHandler` (CI/test) |
| `RunPersistence` | `save_agent_output()`, `save_run_summary()`, `save_artifact_index()`, `finalize_run()` — all file-based YAML |
| LangGraph pipeline | 7 nodes: init, dispatcher, approval_gate, research, builder, reviewer, persist. Conditional routing. |
| `RunState` TypedDict | Shared pipeline state with all input/output/control fields |
| `cli.py` | Full CLI with `--approval-level`, `--criteria`, `--constraint`, `--run-id`, `--no-interactive`, `--no-persist`, `-v` |
| 79 tests | Across 5 test files, all passing |
| Agent definitions | `agents/{role}/agent.md`, `prompt.md`, `policy.md`, `tools.yaml` for all 4 core + 4 future agents |
| Policy files | `approval-matrix.yaml`, `security-rules.yaml`, `data-handling.yaml`, `escalation-rules.yaml`, `naming-conventions.yaml` |
| Skills registry | `skills/registry.yaml` |
| Documentation | `docs/vision.md`, `architecture.md`, `agent-map.md`, `run-lifecycle.md`, `onboarding.md` |
| Templates | `templates/task-brief.md`, `implementation-plan.md`, `research-report.md`, `review-report.md`, `postmortem.md` |
| Utility scripts | `bootstrap.ps1`, `run-tests.ps1`, `lint.ps1`, `create-worktree.ps1` |

---

## 4. What Is Scaffolded (Structure Exists, Not Connected)

| Item | Location | Gap |
|------|----------|-----|
| LangGraph Pydantic schemas | `workflows/langgraph/schemas/task_schema.py` | Defined but not enforced at pipeline boundaries |
| Agent `tools.yaml` | `agents/{role}/tools.yaml` | Files exist per agent, not connected to any tool runtime |
| `AnthropicClient` live calls | `src/ai_ops/llm/client.py` | Code complete but no integration tests (needs API key) |
| Future agent stubs | `agents/browser-operator/`, `agents/comms/`, `agents/knowledge/`, `agents/ops-integration/` | README + definition only, no Python agent class |
| Temporal workflows | `workflows/temporal/README.md` | Placeholder README only |

---

## 5. What Is Deferred (Not Started)

- MCP integration (`integrations/mcp/`)
- n8n integration (`integrations/n8n/`)
- Temporal workflow engine
- Production UI / dashboard
- Revision loops (reviewer → builder retry on FAIL)
- OpenAI / local model LLM providers
- Advanced memory retrieval and pattern matching
- Cost tracking / token budgets
- Scheduling / cron triggers
- Browser automation agent runtime
- Real tool execution by agents (today agents reason but don't run tools)

---

## 6. Exact Commands

```powershell
# All commands from repo root: C:\Users\user\.gemini\antigravity\scratch\ai-ops

# Run tests (fast, no API key needed)
$env:PYTHONPATH = "src"; python -m pytest tests --tb=short
# or:
.\scripts\run-tests.ps1

# Run CLI in stub mode (no API key)
$env:PYTHONPATH = "src"; python -m ai_ops.cli "Research Python web frameworks"

# Run CLI with LLM
$env:PYTHONPATH = "src"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m ai_ops.cli "Build auth module" --criteria "JWT support" --criteria "Password hashing"

# Lint
.\scripts\lint.ps1
# or: python -m ruff check src tests workflows

# Type check
python -m mypy src/ai_ops
```

> [!NOTE]
> `PYTHONPATH=src` is required because the package uses `src/` layout but is not pip-installed in dev. The repo root must also be on `sys.path` for `workflows` package imports; `cli.py` and `dispatch_pipeline.py` handle this via runtime path manipulation.

---

## 7. Key Files

### Source Code (`src/ai_ops/`)

| File | Purpose |
|------|---------|
| `agents/base.py` | `BaseAgent` ABC — `run()` envelope, LLM integration, approval check, prompt loading |
| `agents/dispatcher.py` | Task classification (LLM or heuristic), execution plan generation |
| `agents/research.py` | Research execution, structured findings output |
| `agents/builder.py` | Implementation execution, file change tracking |
| `agents/reviewer.py` | Review execution, verdict (PASS/FAIL/PASS WITH ISSUES) |
| `llm/client.py` | `LLMClient` protocol, `AnthropicClient`, `StubClient`, `create_client()` |
| `llm/prompts.py` | Loads `prompt.md` per agent, builds structured user messages |
| `runtime/approval.py` | `ApprovalHandler` protocol, interactive + auto handlers |
| `runtime/persistence.py` | YAML-based run persistence, finalization, summary writing |
| `cli.py` | CLI entry point — parses args, initializes components, invokes pipeline |

### Orchestration (`workflows/langgraph/`)

| File | Purpose |
|------|---------|
| `graphs/dispatch_pipeline.py` | LangGraph graph: 7 nodes, conditional routing, module-level config via `create_pipeline()` |
| `state/run_state.py` | `RunState` TypedDict — shared state schema for all pipeline nodes |
| `schemas/task_schema.py` | Pydantic validation models (TaskBrief, TaskClassification, ExecutionPlan, etc.) — **not yet enforced** |

### Governance

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Behavioral kernel — rules for any AI agent working in this repo |
| `policies/approval-matrix.yaml` | Which actions require which approval level |
| `agents/{role}/prompt.md` | System prompt sent to LLM for each agent |
| `agents/{role}/tools.yaml` | Tool definitions per agent (not yet connected) |

### Tests

| File | Tests | Covers |
|------|-------|--------|
| `test_agents.py` | 25 | Agent interface, stub execution, approval gating |
| `test_llm_client.py` | 19 | StubClient, factory, prompt loading, message building |
| `test_approval.py` | 13 | Both handlers, all 4 levels |
| `test_persistence.py` | 9 | YAML writing, dir management, finalization |
| `test_pipeline.py` | 13 | End-to-end pipeline, persistence, approval gating |

---

## 8. Known Weak Spots / Risks

1. **Module-level globals in `dispatch_pipeline.py`** — `_llm_client`, `_approval_handler`, `_persistence` are set via `create_pipeline()`. This means you can't safely run two pipelines concurrently in the same process. Adequate for now; will need refactoring for concurrent use.

2. **`sys.path` manipulation** — Both `cli.py` and `dispatch_pipeline.py` prepend to `sys.path` at import time. Works but is fragile. A proper `pip install -e .` or workspace setup would be cleaner.

3. **No revision loop** — If the reviewer returns `FAIL`, the pipeline just records it and ends. There is no `reviewer → builder` retry edge. The routing function `route_after_review` always goes to `persist`.

4. **Schemas not enforced** — `task_schema.py` has Pydantic models for classification, plans, and verdicts, but the pipeline doesn't validate agent outputs against them. A malformed LLM response that passes JSON parsing won't be caught.

5. **No real tool execution** — Agents reason about tasks but cannot actually run tools (linter, tests, file writes, web searches). The `tools.yaml` definitions are documentation only.

6. **`AnthropicClient` untested** — The code is complete but there are zero integration tests. First real test will be the first run with an API key.

7. **Version drift** — `__init__.py` says `0.1.0`, `pyproject.toml` says `0.2.0`.

8. **Windows-only scripts** — `bootstrap.ps1`, `run-tests.ps1`, `lint.ps1` are PowerShell. No bash equivalents.

---

## 9. Next Task

**Enforce Pydantic schema validation at pipeline boundaries.**

Specifically:
- In `dispatcher_node`, validate the dispatcher's `output.result` against `TaskClassification` and `ExecutionPlan` schemas from `task_schema.py`
- In `reviewer_node`, validate against a `ReviewResult` schema (may need to add one)
- Handle validation failures gracefully (log warning, continue with raw dict, add to `errors`)
- Add tests for valid and invalid schema cases

This is the natural next step because:
- The schemas already exist in `task_schema.py`
- Without validation, bad LLM output that happens to be valid JSON silently corrupts downstream state
- It is a contained, testable change that doesn't expand scope
- It directly supports `CLAUDE.md` rule §12 (Completion Integrity) and §9 (Verification Order)
