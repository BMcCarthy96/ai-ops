---
name: scaffold-agent
description: Scaffold a new agent for this AI Ops project following all naming and structure conventions
allowed-tools: Read, Write, Glob, Edit
---

Collect from the user:
- Agent role name (kebab-case, e.g. `browser-operator`)
- Mission statement (one sentence)
- In-scope responsibilities (3-5 bullets)
- Out-of-scope items (2-3 bullets)
- Tool list (names + approval levels)

Then scaffold the following, using `agents/builder/` as the canonical template:

## Files to create

**`agents/<role>/agent.md`** — role definition (identity, mission, scope, escalation triggers, success criteria)

**`agents/<role>/prompt.md`** — system prompt (identity, core behavior, execution modes, JSON output contract, failure handling, style rules)

**`agents/<role>/policy.md`** — policy constraints (approval levels, forbidden actions, escalation chain)

**`agents/<role>/tools.yaml`** — tool definitions (name, description, approval_level for each tool)

**`src/ai_ops/agents/<role_snake>.py`** — Python class extending `BaseAgent`:
- `__init__` sets `AgentRole.<ROLE>`
- `execute()` routes to `_execute_stub()` (implemented) and `_execute_llm()` (stub with TODO)
- `_execute_stub()` returns deterministic output following the same pattern as `ReviewerAgent._execute_stub`
- `_skill_prefix()` returns a short string matching the role

## Changes to existing files

**`src/ai_ops/agents/base.py`** — add `AgentRole.<ROLE> = "<role>"` to the enum

**`workflows/langgraph/graphs/dispatch_pipeline.py`** — add common name aliases to `_AGENT_NAME_ALIASES` for the new role

## Rules
- Mark all LLM mode stubs with `# TODO: implement LLM mode`
- Do not claim LLM mode is implemented if only the stub exists
- Follow naming-conventions.yaml: kebab-case dirs, snake_case Python, PascalCase classes
- Do not add the agent to the LangGraph graph — that is Phase 2 work and must be explicitly requested
