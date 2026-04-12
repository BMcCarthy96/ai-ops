# MCP Integration

> **Status**: 🔶 Placeholder — Not implemented in Phase 1

## Overview

[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) will provide standardized tool access for AI Ops agents. Each agent's tools (defined in `tools.yaml`) will be exposed as MCP tool calls, enabling consistent tool invocation across different LLM providers and agent implementations.

## Planned Architecture

```
Agent (LLM) ──► MCP Client ──► MCP Server ──► Tool Implementation
                                   │
                                   ├── File System Server (read/write)
                                   ├── Git Server (branch, worktree, diff)
                                   ├── Code Analysis Server (lint, typecheck)
                                   ├── Test Runner Server (pytest)
                                   └── Web Search Server (search, read URL)
```

## Phase 2 Plan

1. Set up MCP server for file system operations
2. Set up MCP server for git operations
3. Map each agent's `tools.yaml` to MCP tool definitions
4. Implement approval-level checking in MCP middleware
5. Add logging and audit trail for all MCP tool calls

## Configuration

See `config.yaml` in this directory for the placeholder configuration structure.

## Prerequisites

- MCP SDK (Python)
- Tool implementations for each MCP server
- Approval middleware
- Audit logging integration
