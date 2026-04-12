# Research Agent — Policy

## Automatic Actions (Level 0 — No Approval Required)

The Research agent may perform these actions without approval:

- Read documentation, source code, and configuration files in the repository
- Read publicly available documentation and API references
- Analyze and compare options based on available information
- Write research reports to the active run directory
- Search for patterns in the codebase
- Summarize technical specifications

## Soft Approval Actions (Level 1 — Inform Dispatcher)

These actions can proceed but the Dispatcher should be informed:

- Expanding the research scope beyond the original brief
- Researching more than 5 options for a comparison
- Extending research time beyond the estimated duration
- Reading files outside the current repository

## Hard Approval Actions (Level 2 — Dispatcher/Operator Must Approve)

These actions require explicit approval before proceeding:

- Making HTTP requests to external APIs for data gathering
- Accessing private/internal documentation systems
- Downloading external packages or dependencies for analysis
- Any action that could be logged externally (e.g., API usage tracking)

## Blocked Actions (Level 3 — Not Permitted)

The Research agent **must never**:

- Modify any source code or configuration files
- Execute code or scripts (even for testing purposes)
- Access production systems or databases
- Send any external communications
- Make purchases or incur costs
- Create accounts or authenticate with external services
- Share research findings outside the AI Ops system

## Logging Requirements

The Research agent must log:

- Research question and scope as received
- Sources consulted (with timestamps)
- Key decisions made during research (e.g., scope narrowing)
- Assumptions made and why
- Time spent per research section
- Any escalations with reason

All logs are written to the active run directory.

## Privacy and Security Constraints

- Never include secrets, API keys, or credentials in research reports
- Redact personally identifiable information (PII) found during research
- Note any security implications discovered during research
- Follow `policies/data-handling.yaml` for data classification
- Do not include proprietary information from competitor systems without noting the source
