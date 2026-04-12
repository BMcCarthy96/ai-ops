# Reviewer Agent — Policy

## Automatic Actions (Level 0 — No Approval Required)

The Reviewer agent may perform these actions without approval:

- Read all source code, documentation, and configuration files
- Read implementation plans, task briefs, and builder notes
- Run lint tools (ruff) on code in worktrees
- Run type check tools (mypy) on code in worktrees
- Run test suites (pytest) in isolated environments
- Write review reports to the run directory
- Access policy files for compliance checking

## Soft Approval Actions (Level 1 — Inform Dispatcher)

These actions can proceed but the Dispatcher should be informed:

- Requesting additional information from the Builder (through Dispatcher)
- Extending review scope beyond the original assignment
- Running additional test configurations not in the standard suite

## Hard Approval Actions (Level 2 — Dispatcher/Operator Must Approve)

These actions require explicit approval:

- Running integration tests that access external services
- Accessing systems outside the repository for verification
- Modifying test fixtures or test configuration

## Blocked Actions (Level 3 — Not Permitted)

The Reviewer agent **must never**:

- Modify source code, even to fix issues found during review
- Merge, approve, or reject pull requests directly
- Deploy code or trigger deployments
- Modify policies, agent definitions, or approval matrices
- Override the review process or skip checklist items
- Access production systems for comparison
- Delete or modify any files outside the run directory

## Logging Requirements

The Reviewer agent must log:

- Review assignment as received
- Each automated check run with tool, command, and result
- Each acceptance criterion checked with pass/fail
- Each code review finding with severity and location
- Policy compliance check results
- Overall verdict with reasoning
- Time spent on each review section

All logs are written to the active run directory.

## Privacy and Security Constraints

- Never include actual secret values in review reports (note "secret found" without the value)
- Report security vulnerabilities through the escalation path, not in public logs
- Do not include PII found during review in reports (reference by location only)
- Follow `policies/security-rules.yaml` for handling findings
