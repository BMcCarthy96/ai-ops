---
name: review-run
description: Read and summarize a completed AI Ops run directory
allowed-tools: Bash, Read, Glob
---

Find the target run directory:
- If a run ID is provided, look in `runs/completed/<run-id>/` or `runs/failed/<run-id>/`
- Otherwise, use the most recently modified directory under `runs/completed/` then `runs/failed/`

Read these files (if present):
- `run-summary.yaml` — overall status, agents used, timing
- `dispatcher-output.yaml` — task classification and execution plan
- `research-output.yaml` — research findings (if research ran)
- `builder-output.yaml` — files created, implementation summary
- `reviewer-output.yaml` — verdict, acceptance criteria results, findings

Report one section per agent that ran, using bullet points:

**Run ID**: `<id>`
**Status**: completed / failed / needs_revision

**Dispatcher**: task type, required agents, subtask count

**Research** (if ran): key findings, gaps

**Builder** (if ran): files created, deviations from plan

**Reviewer** (if ran):
- Verdict: PASS / PASS WITH ISSUES / FAIL
- Criteria results (PASS/FAIL/PARTIAL for each)
- Findings (severity, file, description)

**Errors / Escalations**: list any items from `errors` or `escalations` fields
