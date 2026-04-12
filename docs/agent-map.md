# Agent Map

## Overview

This document maps all agents in the AI Ops system, their status, and their relationships.

## Active Agents (Phase 1)

### Dispatcher
- **Role**: Central coordinator
- **Status**: ✅ Defined, 🔶 Scaffolded in Python
- **Delegates to**: Research, Builder, Reviewer
- **Reports to**: Operator
- **Definition**: [agents/dispatcher/](../agents/dispatcher/)

### Research
- **Role**: Information gathering and analysis
- **Status**: ✅ Defined, 🔶 Scaffolded in Python
- **Receives from**: Dispatcher
- **Reports to**: Dispatcher
- **Definition**: [agents/research/](../agents/research/)

### Builder
- **Role**: Implementation and code creation
- **Status**: ✅ Defined, 🔶 Scaffolded in Python
- **Receives from**: Dispatcher
- **Reports to**: Dispatcher
- **Definition**: [agents/builder/](../agents/builder/)

### Reviewer
- **Role**: Quality assurance and validation
- **Status**: ✅ Defined, 🔶 Scaffolded in Python
- **Receives from**: Dispatcher
- **Reports to**: Dispatcher
- **Definition**: [agents/reviewer/](../agents/reviewer/)

## Planned Agents (Phase 2+)

### Browser Operator
- **Role**: Web interaction, UI validation, data extraction
- **Status**: ⬜ Placeholder only
- **Definition**: [agents/browser-operator/](../agents/browser-operator/)

### Ops Integration
- **Role**: Infrastructure and deployment operations
- **Status**: ⬜ Placeholder only
- **Definition**: [agents/ops-integration/](../agents/ops-integration/)

### Comms
- **Role**: Communication drafting and distribution
- **Status**: ⬜ Placeholder only
- **Definition**: [agents/comms/](../agents/comms/)

### Knowledge
- **Role**: Knowledge management, documentation, postmortems
- **Status**: ⬜ Placeholder only
- **Definition**: [agents/knowledge/](../agents/knowledge/)

## Agent Interaction Matrix

| From \ To    | Dispatcher | Research | Builder | Reviewer | Operator |
|-------------|-----------|---------|---------|---------|---------|
| Operator    | ✅ tasks   | —       | —       | —       | —       |
| Dispatcher  | —         | ✅ assign| ✅ assign| ✅ assign| ✅ escalate |
| Research    | ✅ report  | —       | —       | —       | ✅ escalate |
| Builder     | ✅ report  | —       | —       | —       | ✅ escalate |
| Reviewer    | ✅ report  | —       | —       | —       | ✅ escalate |

## Communication Pattern

All agent communication flows through the Dispatcher. Agents do not communicate directly with each other. Any agent can escalate directly to the Operator when policy requires it.
