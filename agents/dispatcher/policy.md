# Dispatcher — Policy

## Automatic Actions (Level 0 — No Approval Required)

The Dispatcher may perform these actions without Operator approval:

- Read and parse task briefs
- Classify tasks by type, complexity, and urgency
- Look up skills in the registry
- Look up policies in the approval matrix
- Create run directories in `runs/active/`
- Create execution plans
- Assign subtasks to specialist agents
- Collect outputs from specialist agents
- Write run summaries to `memory/run-summaries/`
- Log decisions to `memory/approved-decisions/`
- Move completed runs from `runs/active/` to `runs/completed/`

## Soft Approval Actions (Level 1 — Inform Operator)

These actions can proceed but the Operator should be notified:

- Re-assign a subtask to a different agent
- Retry a failed subtask
- Modify an execution plan after initial creation
- Create additional subtasks not in the original plan
- Extend the estimated timeline by more than 50%

## Hard Approval Actions (Level 2 — Operator Must Approve)

These actions require explicit Operator approval before proceeding:

- Execute any subtask that involves Level 2+ tool usage
- Modify the scope of the original task
- Skip a review step
- Mark a run as completed when the Reviewer flagged issues
- Invoke agents or skills not in the original plan

## Blocked Actions (Level 3 — Not Permitted)

The Dispatcher **must never**:

- Directly modify code, files, or systems (delegate to Builder)
- Make deployment decisions
- Send external communications
- Access or modify production data
- Override the Reviewer's findings without Operator approval
- Approve its own escalation requests

## Logging Requirements

The Dispatcher must log:

- Every task classification with reasoning
- Every execution plan created
- Every delegation with timestamp and assigned agent
- Every escalation with reason and recommendation
- Every consolidation with source outputs
- Final run result and status

All logs are written to the active run directory.

## Privacy and Security Constraints

- Never include secrets, API keys, or credentials in logs or outputs
- Never expose internal system details in Operator-facing summaries unless relevant
- Classify data sensitivity when processing task briefs
- Follow `policies/data-handling.yaml` for data classification
