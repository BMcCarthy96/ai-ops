# Temporal Workflows

> **Status**: ⬜ Deferred — Not implemented in Phase 1

## Future Purpose

[Temporal](https://temporal.io/) will provide durable, long-running workflow execution for AI Ops. While LangGraph handles the agent orchestration graph, Temporal will handle workflows that need to:

- Run for hours or days
- Survive process restarts
- Handle complex retry and compensation logic
- Coordinate across multiple services

## Planned Use Cases

1. **Multi-day research projects**: Research tasks that span multiple sessions
2. **Deployment pipelines**: Long-running deploy → verify → rollback workflows
3. **Scheduled operations**: Recurring maintenance and reporting tasks
4. **Cross-system orchestration**: Workflows that span multiple external systems

## Prerequisites

- Temporal server deployment
- Python Temporal SDK integration
- Workflow-to-LangGraph bridge
- Durable state management strategy

## Relationship to LangGraph

```
LangGraph: Agent orchestration (Dispatcher → Research → Builder → Reviewer)
Temporal:  Durable workflow wrapper (retry, state persistence, long-running)

Temporal Workflow
  └── LangGraph Execution (one or more agent pipeline runs)
       ├── Dispatcher
       ├── Research
       ├── Builder
       └── Reviewer
```

LangGraph handles the "what agents do." Temporal handles the "making sure it completes reliably."
