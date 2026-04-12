# Run Lifecycle

## What Is a Run?

A **run** is a single end-to-end execution of a task through the AI Ops system. Every task the operator submits creates a run. Runs are tracked in the `runs/` directory and follow a defined lifecycle.

## Lifecycle Stages

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────────┐
│  INTAKE  │───►│ PLANNING │───►│EXECUTION │───►│  REVIEW  │───►│CONSOLIDATION │───►│MEMORY UPDATE │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────────┘    └──────────────┘
```

### 1. Intake
- **Who**: Dispatcher
- **What happens**:
  - Operator submits a task (natural language or structured brief)
  - Dispatcher receives and classifies the task
  - A run directory is created: `runs/active/{run-id}/`
  - The task brief is saved to the run directory
  - Dispatcher identifies required skills and agents
  - Approval level is determined from `policies/approval-matrix.yaml`
- **Outputs**: Run directory, classified task, initial plan

### 2. Planning
- **Who**: Dispatcher (with input from Research if needed)
- **What happens**:
  - Dispatcher breaks the task into subtasks
  - Each subtask is assigned to a specialist agent
  - Execution order and dependencies are defined
  - If the plan requires Level 2+ approval, it is presented to the Operator
- **Outputs**: Execution plan with subtask assignments

### 3. Execution
- **Who**: Specialist agents (Research, Builder, etc.)
- **What happens**:
  - Each assigned agent receives its subtask
  - Agent selects skills from the registry
  - Agent executes using allowed tools (per its `tools.yaml`)
  - Agent produces structured output (per its `prompt.md` format)
  - Approval gates are checked per `policies/approval-matrix.yaml`
  - Progress is logged to the run directory
- **Outputs**: Agent artifacts, implementation code, findings, etc.

### 4. Review
- **Who**: Reviewer agent
- **What happens**:
  - Reviewer receives all execution outputs
  - Checks against acceptance criteria from the original task
  - Runs automated checks (lint, tests) if applicable
  - Identifies regressions, missing criteria, or policy violations
  - Produces a structured review report
- **Outputs**: Review report with pass/fail/issues

### 5. Consolidation
- **Who**: Dispatcher
- **What happens**:
  - Dispatcher collects all agent outputs and the review report
  - Produces a consolidated summary for the Operator
  - If the review found issues, escalates for re-work or Operator decision
  - Presents final results to the Operator
- **Outputs**: Consolidated result, operator-facing summary

### 6. Memory Update
- **Who**: Dispatcher (or Knowledge agent in future)
- **What happens**:
  - Run summary is written to `memory/run-summaries/`
  - Key decisions are recorded in `memory/approved-decisions/`
  - Patterns are extracted and stored in `memory/patterns/`
  - Run directory moves from `runs/active/` to `runs/completed/` (or `runs/failed/`)
- **Outputs**: Updated memory, archived run

## Run Directory Structure

```
runs/active/{run-id}/
├── task-brief.md          # Original task description
├── plan.md                # Execution plan
├── research-output.md     # Research agent findings (if applicable)
├── build-output.md        # Builder agent artifacts (if applicable)
├── review-report.md       # Reviewer agent report
├── consolidation.md       # Final consolidated summary
└── metadata.yaml          # Run metadata (status, timestamps, agents used)
```

## Run States

| State | Location | Meaning |
|-------|----------|---------|
| `active` | `runs/active/` | Currently being worked on |
| `completed` | `runs/completed/` | Successfully finished |
| `failed` | `runs/failed/` | Failed or abandoned |

## Failure Handling

- If an agent fails, it reports a structured failure to the Dispatcher
- The Dispatcher can retry, reassign, or escalate to the Operator
- If the run cannot be completed, it moves to `runs/failed/` with a failure summary
- Failed runs still update memory (lessons learned)
