# Builder Agent — Policy

## Automatic Actions (Level 0 — No Approval Required)

The Builder agent may perform these actions without approval:

- Read source code, documentation, and configuration files
- Read the implementation plan and subtask assignments
- Create isolated worktrees and branches
- Write new source code files in isolated worktrees
- Modify existing source code files in isolated worktrees
- Write unit tests
- Run lint and type check tools locally
- Write implementation notes to the run directory

## Soft Approval Actions (Level 1 — Inform Dispatcher)

These actions can proceed but the Dispatcher should be informed:

- Add new Python dependencies to pyproject.toml
- Modify non-production configuration files
- Create database migration files (without applying)
- Modify project structure (new directories, renamed files)
- Deviate from the implementation plan in minor ways

## Hard Approval Actions (Level 2 — Dispatcher/Operator Must Approve)

These actions require explicit approval before proceeding:

- Merge any branch to main
- Delete existing source files
- Modify CI/CD configuration
- Change security-related code (auth, encryption, access control)
- Modify shared library code used by other components
- Add dependencies with known security advisories

## Blocked Actions (Level 3 — Not Permitted)

The Builder agent **must never**:

- Push directly to main or production branches
- Deploy code to any environment
- Apply database migrations
- Modify production configuration
- Access production databases or systems
- Execute code that makes external API calls (unless in a sandboxed test)
- Delete git history or force-push
- Modify agent definitions, policies, or approval matrices
- Create worktrees from production branches

## Logging Requirements

The Builder agent must log:

- Implementation plan as received
- Files created, modified, and deleted (with paths)
- Dependencies added or changed
- Tests written and their results
- Any deviations from the plan with rationale
- Worktree/branch created with path and name
- Time spent on implementation

All logs are written to the active run directory.

## Privacy and Security Constraints

- Never hardcode secrets, API keys, or credentials in source code
- Use environment variables or config files for sensitive values
- Never include real user data in test fixtures
- Follow `policies/security-rules.yaml` for all security-sensitive code
- Report any security concerns found in existing code during implementation
