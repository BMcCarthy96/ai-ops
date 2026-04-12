# Memory Model

## Overview

AI Ops uses a three-tier memory model to maintain context across runs, learn from past work, and improve over time. In Phase 1, all memory is file-based (Markdown and YAML stored in the `memory/` directory). Future phases may add vector stores, databases, or search indexes.

## Memory Tiers

### 1. Working Memory

**What**: The current state of an active run.

**Where**: `runs/active/{run-id}/` directory

**Contents**:
- Task brief
- Execution plan
- Agent outputs (in progress)
- Current status and decisions

**Lifecycle**: Created at run intake, updated during execution, archived at completion.

**Phase 1 implementation**: File-based. Each run directory contains all working state.

**Future**: LangGraph state objects will serve as structured working memory during orchestration.

### 2. Episodic Memory

**What**: Records of past runs — what was done, what happened, and what was decided.

**Where**: `memory/run-summaries/`

**Contents**:
Each run summary includes:
- Run ID and dates
- Original task brief (condensed)
- Agents involved
- Key decisions made
- Outcomes (success/failure)
- Lessons learned
- Duration and complexity

**Format**:
```yaml
# memory/run-summaries/{run-id}.yaml
run_id: "2026-04-12-scaffold-auth-module"
date_start: "2026-04-12T10:00:00Z"
date_end: "2026-04-12T14:30:00Z"
status: completed  # completed | failed | partial
task_summary: "Scaffold authentication module with JWT support"
agents_used: [dispatcher, research, builder, reviewer]
skills_used: [research.compare.tools, coding.scaffold.service, qa.review.implementation]
decisions:
  - decision: "Use PyJWT over python-jose"
    reason: "Better maintained, simpler API"
    approval_level: 1
outcome: "Auth module scaffolded and reviewed. Ready for integration."
issues: []
lessons:
  - "JWT library comparison took longer than expected due to conflicting docs"
```

**Lifecycle**: Created when a run completes or fails. Never deleted, only archived.

**How it's used**:
- Dispatcher checks past summaries for similar tasks
- Knowledge agent (future) extracts patterns
- Operator reviews history

### 3. Semantic Memory

**What**: Patterns, best practices, and approved decisions that transcend individual runs.

**Where**: 
- `memory/patterns/` — Reusable patterns extracted from runs
- `memory/approved-decisions/` — Decisions that set precedent

**Patterns format**:
```yaml
# memory/patterns/{pattern-name}.yaml
name: "jwt-library-selection"
category: "technology-choice"
description: "When selecting a JWT library for Python, prefer PyJWT"
evidence:
  - run_id: "2026-04-12-scaffold-auth-module"
    finding: "PyJWT is better maintained with simpler API"
applicability: "Python projects requiring JWT authentication"
last_verified: "2026-04-12"
confidence: high  # low | medium | high
```

**Approved decisions format**:
```yaml
# memory/approved-decisions/{decision-name}.yaml
name: "use-ruff-for-linting"
decision: "Use ruff as the primary Python linter"
date: "2026-04-12"
approved_by: operator
rationale: "Fast, comprehensive, drop-in replacement for flake8+isort+pyupgrade"
scope: "All Python code in ai-ops"
supersedes: null
```

**Lifecycle**: Created by extraction from run summaries. Periodically reviewed and updated.

**How it's used**:
- Agents check patterns before making decisions
- Dispatcher references approved decisions during planning
- Research agent uses patterns to contextualize findings

## Phase 1 Status

| Component | Status | Implementation |
|-----------|--------|----------------|
| Working memory | ✅ Implemented | Run directories in `runs/active/` |
| Episodic memory | 🔶 Scaffolded | Directory structure + format defined |
| Semantic memory | 🔶 Scaffolded | Directory structure + format defined |
| Memory search | ⬜ Deferred | Future: embedding-based semantic search |
| Memory pruning | ⬜ Deferred | Future: automated summarization and cleanup |
| Memory indexing | ⬜ Deferred | Future: searchable index of all memories |

## Future Enhancements

1. **Embedding-based search**: Use vector embeddings to find relevant past runs and patterns
2. **Automated pattern extraction**: Knowledge agent periodically extracts patterns from run summaries
3. **Memory decay**: Reduce confidence of old patterns that haven't been re-verified
4. **Cross-referencing**: Link related memories, decisions, and patterns
5. **Memory visualization**: Dashboard showing memory growth and connections
