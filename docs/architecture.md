# Architecture

## System Overview

AI Ops is a multi-agent system with a hub-and-spoke architecture. The **Dispatcher** is the hub. Specialist agents are the spokes. The human **Operator** sits above the Dispatcher as the ultimate authority.

```
┌─────────────────────────────────────────────────┐
│                   OPERATOR                       │
│              (Human Director)                    │
└──────────────────┬──────────────────────────────┘
                   │ task / approval / override
                   ▼
┌─────────────────────────────────────────────────┐
│                 DISPATCHER                       │
│  intake → classify → plan → delegate → collect   │
└────┬──────────┬──────────┬──────────┬───────────┘
     │          │          │          │
     ▼          ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
 │Research│ │Builder │ │Reviewer│ │ Future │
 │ Agent  │ │ Agent  │ │ Agent  │ │ Agents │
 └────────┘ └────────┘ └────────┘ └────────┘
     │          │          │
     ▼          ▼          ▼
 ┌────────────────────────────────────────────────┐
 │              SKILLS REGISTRY                    │
 │  research.compare.tools, coding.scaffold.svc,  │
 │  qa.review.implementation, ...                  │
 └────────────────────────────────────────────────┘
     │          │          │
     ▼          ▼          ▼
 ┌────────────────────────────────────────────────┐
 │              TOOLS & INTEGRATIONS               │
 │  MCP servers, n8n workflows, file system,       │
 │  git, browser, APIs                             │
 └────────────────────────────────────────────────┘
```

## Layers

### 1. Operator Layer
- The human operator issues tasks, reviews work, and makes approval decisions
- Operates via Antigravity (the primary interface)
- Has Level 3 authority (can authorize any action)

### 2. Orchestration Layer
- **Current**: Direct function calls between agent stubs
- **Future**: LangGraph for stateful multi-step orchestration
- **Later**: Temporal for long-running durable workflows

### 3. Agent Layer
- Each agent is defined by:
  - `agent.md` — Mission, scope, inputs/outputs
  - `prompt.md` — System prompt, output format, execution checklist
  - `policy.md` — Permissions, constraints, logging requirements
  - `tools.yaml` — Allowed tools and approval modes
- Agents invoke **skills** to do work
- Agents follow **policies** for governance

### 4. Skills Layer
- Skills are reusable capabilities (e.g., `research.compare.tools`)
- Each skill defines inputs, outputs, tools, done criteria, and failure behavior
- Multiple agents can invoke the same skill
- Skills are registered in `skills/registry.yaml`

### 5. Policy Layer
- `approval-matrix.yaml` — What requires human approval and at what level
- `escalation-rules.yaml` — When and how to escalate to the operator
- `security-rules.yaml` — What is forbidden, what requires extra scrutiny
- `data-handling.yaml` — How data is classified and handled
- `naming-conventions.yaml` — How things are named across the system

### 6. Memory Layer
- **Working memory**: Current run state (in LangGraph state or run directory)
- **Episodic memory**: Run summaries stored in `memory/run-summaries/`
- **Semantic memory**: Patterns and approved decisions in `memory/patterns/` and `memory/approved-decisions/`

### 7. Integration Layer
- **MCP**: Tool access protocol for agents (placeholder in Phase 1)
- **n8n**: Event-driven automation and external triggers (placeholder in Phase 1)

## Data Flow

```
1. Operator submits task
2. Dispatcher receives and classifies
3. Dispatcher creates run directory in runs/active/
4. Dispatcher plans subtasks and assigns agents
5. Each agent:
   a. Reads its assignment
   b. Selects skills from registry
   c. Executes using allowed tools
   d. Produces structured output
   e. Reports back to Dispatcher
6. Dispatcher consolidates results
7. Reviewer checks work against acceptance criteria
8. Dispatcher presents final output to Operator
9. Run moves to runs/completed/ (or runs/failed/)
10. Memory is updated
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Hub-and-spoke, not peer-to-peer | Simpler to govern; Dispatcher is the single point of coordination |
| Config-as-code for policies | Policies are versionable, diffable, and machine-readable |
| Skills separate from agents | Enables reuse; agents are roles, skills are capabilities |
| YAML for config, Markdown for docs | Human-readable, agent-readable, git-friendly |
| Python for runtime | Best ecosystem for LLM tooling (LangChain, LangGraph, etc.) |
| Isolated worktrees for builds | Prevents Builder from contaminating main branch |

## Phase 1 Boundaries

- No live LLM calls (agent logic is stubbed)
- No production deployments
- No external system integrations
- No persistent database (file-based memory only)
- No real-time dashboard
