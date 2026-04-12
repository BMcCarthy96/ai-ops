# Vision

## Why AI Ops Exists

Software operations are full of structured, repeatable work that benefits from explicit governance: research tasks, code scaffolding, implementation review, status reporting, deployment coordination. These tasks have clear inputs, outputs, constraints, and approval requirements.

AI Ops is a platform where a human operator directs a team of specialized AI agents to perform this work — with explicit policies, approval gates, audit trails, and structured memory.

## Core Beliefs

1. **The human is the operator, not the passenger.** Agents propose; humans decide. The system escalates uncertainty, never hides it.

2. **Agents are roles, not monoliths.** Each agent has a narrow mission, explicit permissions, and clear boundaries. Agents do not improvise outside their scope.

3. **Skills are reusable capabilities.** The same skill (e.g., "compare tools") can be invoked by different agents. Skills are the unit of work; agents are the unit of accountability.

4. **Policies are code.** Approval levels, security constraints, and escalation rules are defined in configuration, not in prose or tribal knowledge.

5. **Memory is explicit.** Decisions, run summaries, and patterns are written down. Nothing important lives only in a conversation context window.

6. **Structure enables autonomy.** The more explicit the rules, the more safely agents can operate with minimal supervision.

## Where This Is Going

Phase 1 establishes the structural foundation. Future phases will add:

- **LangGraph orchestration** — Stateful, resumable multi-agent workflows
- **MCP integration** — Standardized tool access for agents
- **n8n automation** — Event-driven triggers and external system integration
- **Temporal workflows** — Long-running, durable task execution
- **Expanded agent team** — Browser operator, comms, knowledge management, ops integration
- **Dashboard** — Operator visibility into active runs, decisions, and agent performance

## Success Criteria

AI Ops succeeds when:

- A non-trivial task can be described once and executed by the agent team with minimal operator intervention
- Every agent action is traceable to a policy and approval level
- The operator can leave and return without losing context
- New agents and skills can be added without restructuring the platform
- The system honestly represents what it can and cannot do
