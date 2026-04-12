# AI Ops

A multi-agent AI operations system for structured, policy-governed task execution.

## What This Is

AI Ops is an internal platform where a human operator directs work through a **Dispatcher** agent that classifies, plans, delegates, and consolidates work across specialist agents. Each agent has explicit roles, tools, permissions, and policies.

This repository is the **Phase 1 foundation** — the structural, policy, and scaffolding layer that future orchestration (LangGraph), integration (MCP, n8n), and workflow (Temporal) layers will build on.

## Phase 1 Scope

| Area | Status |
|------|--------|
| Repository structure | ✅ Implemented |
| Core documentation | ✅ Implemented |
| Agent definitions (Dispatcher, Research, Builder, Reviewer) | ✅ Implemented |
| Policy files + approval matrix | ✅ Implemented |
| Skills registry | ✅ Implemented |
| Templates | ✅ Implemented |
| Memory model documentation | ✅ Implemented |
| Utility scripts | ✅ Implemented |
| LangGraph orchestration scaffold | 🔶 Scaffolded |
| Python agent base classes | 🔶 Scaffolded |
| MCP / n8n integration placeholders | 🔶 Scaffolded |
| Temporal workflows | ⬜ Deferred |
| Production UI | ⬜ Deferred |

## Architecture

```
Operator (You)
    │
    ▼
Dispatcher ──────► Research
    │                 │
    │                 ▼
    │              Builder
    │                 │
    │                 ▼
    └────────────► Reviewer
                      │
                      ▼
                  Consolidation
```

See [docs/architecture.md](docs/architecture.md) for full details.

## Repository Layout

```
ai-ops/
├── agents/          # Agent definitions (docs, policies, tools)
├── skills/          # Reusable capability registry
├── workflows/       # Orchestration scaffolds (LangGraph, Temporal)
├── integrations/    # External system placeholders (MCP, n8n)
├── memory/          # Run history and decision records
├── policies/        # Global governance rules
├── templates/       # Standardized document templates
├── runs/            # Task execution directories
├── scripts/         # Setup and utility scripts
├── docs/            # Project documentation
└── src/ai_ops/      # Python runtime code
```

## Quick Start

```powershell
# 1. Clone and enter repo
cd ai-ops

# 2. Run bootstrap
.\scripts\bootstrap.ps1

# 3. Run tests
.\scripts\run-tests.ps1

# 4. Run lint
.\scripts\lint.ps1
```

## Key Documents

- [Vision](docs/vision.md) — Why this exists
- [Architecture](docs/architecture.md) — How it works
- [Agent Map](docs/agent-map.md) — Who does what
- [Run Lifecycle](docs/run-lifecycle.md) — How work flows
- [Onboarding](docs/onboarding.md) — How to get started
- [Approval Matrix](policies/approval-matrix.yaml) — What requires approval

## License

Internal use only. Not open source.
