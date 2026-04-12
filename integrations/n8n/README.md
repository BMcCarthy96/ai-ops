# n8n Integration

> **Status**: 🔶 Placeholder — Not implemented in Phase 1

## Overview

[n8n](https://n8n.io/) will provide event-driven automation and external system integration for AI Ops. It will handle triggers (webhooks, schedules, events) and connect to external services that agents need to interact with.

## Planned Use Cases

1. **Task Intake Automation**: Receive tasks from external systems (Slack, email, ticketing) and create task briefs
2. **Status Notifications**: Send status updates when runs complete or fail
3. **Webhook Management**: Configure and manage webhooks between systems
4. **Scheduling**: Trigger periodic tasks (e.g., daily reports, health checks)
5. **External API Integration**: Bridge to services that agents need (with approval gates)

## Planned Architecture

```
External Systems ──► n8n Workflows ──► AI Ops Dispatcher
                                           │
AI Ops Results ──► n8n Workflows ──► External Systems
```

## Phase 2 Plan

1. Deploy n8n instance (self-hosted)
2. Create intake workflow for task submission
3. Create notification workflow for run completion
4. Integrate with approval matrix for external actions
5. Add audit logging for all n8n workflow executions

## Configuration

See `config.yaml` in this directory for the placeholder configuration structure.

## Prerequisites

- n8n instance (self-hosted or cloud)
- Webhook endpoints for AI Ops
- Authentication tokens for external services
- Network access to required external systems
