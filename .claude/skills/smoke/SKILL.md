---
name: smoke
description: Run the AI Ops smoke test suite against the current codebase
allowed-tools: Bash
---

Run the full test suite for this AI Ops project:

```bash
PYTHONPATH=src /home/mccarthyb/miniforge3/envs/pl-bind/bin/python3.11 \
  -m pytest tests/ --tb=short -q
```

Report:
- Total passing / failing count
- Any failures with file:line context and the exact assertion or error
- Whether the suite is fully clean or needs attention
