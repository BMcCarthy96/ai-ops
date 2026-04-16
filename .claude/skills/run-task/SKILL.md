---
name: run-task
description: Run the AI Ops pipeline CLI with a task description and acceptance criteria
allowed-tools: Bash, Read, Glob
---

Ask the user for (or accept inline):
- Task description (required)
- Acceptance criteria (optional, repeatable)
- Approval level (optional, default: 0)
- Verbosity (optional, default: -v)

Then invoke the AI Ops CLI:

```bash
PYTHONPATH=src /home/mccarthyb/miniforge3/envs/pl-bind/bin/python3.11 \
  -m ai_ops.cli \
  --task-description "<desc>" \
  [--criteria "<criterion1>"] \
  [--criteria "<criterion2>"] \
  [--approval-level 0] \
  [-v]
```

After the run completes:
1. Find the most recently modified directory under `runs/completed/` (or `runs/failed/` on failure)
2. Read `run-summary.yaml` and `reviewer-output.yaml` from that directory
3. Report: run ID, agents used, reviewer verdict, files created, any errors or escalations
