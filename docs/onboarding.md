# Onboarding

## Welcome to AI Ops

This guide will help you understand the system, navigate the repository, and start working with the agent team.

## Prerequisites

- Python 3.11 or higher
- Git
- A terminal (PowerShell on Windows)
- Familiarity with YAML and Markdown

## Repository Tour

### Start Here
1. **[README.md](../README.md)** — Project overview and quick start
2. **[docs/vision.md](vision.md)** — Why this exists
3. **[docs/architecture.md](architecture.md)** — How the system works
4. **[docs/agent-map.md](agent-map.md)** — Who does what

### Understand the Agents
Each agent lives in `agents/{name}/` with four files:
- `agent.md` — Mission, scope, responsibilities, inputs/outputs
- `prompt.md` — System prompt and output format
- `policy.md` — What the agent can and cannot do
- `tools.yaml` — Allowed tools and their approval modes

Start with the [Dispatcher](../agents/dispatcher/agent.md) — it's the central coordinator.

### Understand the Policies
- `policies/approval-matrix.yaml` — The most important policy file. Defines what actions require human approval.
- `policies/escalation-rules.yaml` — When agents must stop and ask for help.
- `policies/security-rules.yaml` — Hard boundaries that cannot be crossed.

### Understand the Skills
- `skills/registry.yaml` — The catalog of reusable capabilities that agents can invoke.

### Understand the Workflow
- `docs/run-lifecycle.md` — How a task flows from intake to completion.

## Setup

```powershell
# Clone the repository (or navigate to it)
cd ai-ops

# Run the bootstrap script
.\scripts\bootstrap.ps1

# Verify setup
.\scripts\run-tests.ps1
```

## How to Submit a Task

In Phase 1, tasks are submitted by creating a task brief:

1. Copy `templates/task-brief.md`
2. Fill in the required fields
3. Place it in a new run directory: `runs/active/{descriptive-name}/`
4. Direct the Dispatcher to process it

In future phases, this will be automated through the orchestration layer.

## How to Add a New Agent

1. Create a new directory under `agents/`
2. Create the four required files: `agent.md`, `prompt.md`, `policy.md`, `tools.yaml`
3. Follow the patterns established by the existing agents
4. Register any new skills in `skills/registry.yaml`
5. Update `docs/agent-map.md`

## How to Add a New Skill

1. Add an entry to `skills/registry.yaml`
2. Define: name, category, description, inputs, outputs, tools, done criteria, failure behavior
3. Reference it from the relevant agent's `tools.yaml`

## Key Principles

1. **Read before you act.** Understand the policies and approval matrix before making changes.
2. **Escalate uncertainty.** If you're not sure, ask the operator.
3. **Log everything.** Every decision and action should be traceable.
4. **Don't improvise outside scope.** Each agent has a defined mission. Stay in lane.
5. **Keep it boring.** Readable, predictable code and config over clever solutions.
